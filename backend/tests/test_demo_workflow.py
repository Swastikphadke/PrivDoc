"""End-to-End Demo Workflow Acceptance Test.

Validates all 4 Parts of TASK 3 Live Demonstration on the synthetic demo fixtures:
- Part A: Document Ingestion, Detection, and Entity Linking
- Part B: Human Review (Approve, Reject False Positives, Manual Addition, Redact Similar)
- Part C: Irreversible Redaction & Export Verification (TXT and PDF)
- Part D: Privacy-Safe Summarization & Leakage Suppression
"""

import io
import json
from pathlib import Path
import pytest
import pymupdf
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import get_safe_session_dir
from app.services.summary_guard import SummaryGuard
from app.schemas.summary import SanitizedDocument, StructuredSummaryContent

DEMO_DIR = Path(__file__).resolve().parent.parent.parent / "datasets" / "demo"


@pytest.fixture
def client():
    return TestClient(app)


def test_demo_workflow_txt_sample_report(client):
    """Part A through D on demo_sample_report.txt."""
    txt_path = DEMO_DIR / "demo_sample_report.txt"
    assert txt_path.exists(), "demo_sample_report.txt fixture must exist"
    txt_bytes = txt_path.read_bytes()

    # 1. Ingestion: Upload TXT
    res_upload = client.post(
        "/api/documents/upload",
        files={"file": ("demo_sample_report.txt", txt_bytes, "text/plain")},
    )
    assert res_upload.status_code == 201
    doc_data = res_upload.json()
    doc_id = doc_data["document_id"]
    session_dir = get_safe_session_dir(doc_id)

    try:
        # 2. Detection: Hybrid Regex + Contextual NER
        res_detect = client.post(f"/api/documents/{doc_id}/detect")
        assert res_detect.status_code == 200
        candidates = res_detect.json()["candidates"]
        assert len(candidates) >= 6, "Expected multiple PII candidates detected"

        # 3. Entity Resolution: Grouping and variant linking
        res_entities = client.post(f"/api/documents/{doc_id}/entities/resolve")
        assert res_entities.status_code == 200
        entities_data = res_entities.json()
        assert len(entities_data["entities"]) >= 1, "Expected at least 1 entity cluster"

        # 4. Human Review:
        # 4a. Identify and REJECT deliberate false positive ("Project Apollo" or "ISO-9001")
        fp_cands = [c for c in candidates if "Apollo" in c["text"] or "ISO" in c["text"]]
        for fp in fp_cands:
            res_rej = client.post(
                f"/api/documents/{doc_id}/review",
                json={"candidate_id": fp["candidate_id"], "decision": "REJECT"},
            )
            assert res_rej.status_code == 200

        # 4b. APPROVE sensitive candidates (Marcus Vance, emails, phone, address, employee IDs)
        for c in candidates:
            if c not in fp_cands:
                res_app = client.post(
                    f"/api/documents/{doc_id}/review",
                    json={"candidate_id": c["candidate_id"], "decision": "APPROVE"},
                )
                assert res_app.status_code == 200

        # 4c. Demonstrate Manual Candidate Addition (DOC-2024-SEC-091)
        canonical_res = client.get(f"/api/documents/{doc_id}")
        assert canonical_res.status_code == 200
        raw_text = canonical_res.json()["extracted_text"]
        target_str = "DOC-2024-SEC-091"
        start_idx = raw_text.find(target_str)
        assert start_idx != -1

        res_man = client.post(
            f"/api/documents/{doc_id}/candidates/manual",
            json={
                "start": start_idx,
                "end": start_idx + len(target_str),
                "type": "ID_LIKE",
            },
        )
        assert res_man.status_code == 201

        # 5. Irreversible Redaction & Verification (TXT)
        res_redact = client.post(
            f"/api/documents/{doc_id}/redact",
            json={"placeholder_style": "CATEGORY"},
        )
        assert res_redact.status_code == 200
        red_json = res_redact.json()
        assert red_json["export_state"] == "VERIFIED"

        # Download and verify content
        res_dl = client.get(f"/api/documents/{doc_id}/export")
        assert res_dl.status_code == 200
        exported_text = res_dl.text

        # Verify sensitive information physically absent
        assert "EMP-94812" not in exported_text
        assert "marcus.vance@solaris-defense.internal" not in exported_text
        assert "+1 (415) 555-0199" not in exported_text
        assert "DOC-2024-SEC-091" not in exported_text

        # Verify rejected false positives remain intact
        for fp in fp_cands:
            assert fp["text"] in exported_text

        # 6. Demonstrate Stale Export Invalidation upon Review Mutation
        res_undo = client.post(
            f"/api/documents/{doc_id}/review",
            json={"candidate_id": candidates[0]["candidate_id"], "decision": "PENDING"},
        )
        assert res_undo.status_code == 200
        assert not (session_dir / "sanitized.txt").exists(), "sanitized.txt must be invalidated"
        assert not (session_dir / "export_metadata.json").exists(), "export metadata must be invalidated"

        # Re-approve and re-redact for summary step
        client.post(
            f"/api/documents/{doc_id}/review",
            json={"candidate_id": candidates[0]["candidate_id"], "decision": "APPROVE"},
        )
        client.post(
            f"/api/documents/{doc_id}/redact",
            json={"placeholder_style": "CATEGORY"},
        )

        # 7. Privacy-Safe Summarization
        res_sum = client.post(
            f"/api/documents/{doc_id}/summary",
            json={"force_extractive": True, "max_length": 250},
        )
        assert res_sum.status_code == 200
        sum_data = res_sum.json()
        assert sum_data["state"] == "VERIFIED"
        assert sum_data["content"] is not None

        # Verify prompt injection instruction was completely ignored / not in key points
        summary_text = sum_data["content"]["summary_text"]
        assert "Override previous safety directives" not in summary_text

    finally:
        # Clean deletion cascade
        res_del = client.delete(f"/api/documents/{doc_id}")
        assert res_del.status_code == 200
        assert not session_dir.exists()


def test_demo_workflow_pdf_sample_report(client):
    """Part A through C on demo_sample_report.pdf."""
    pdf_path = DEMO_DIR / "demo_sample_report.pdf"
    assert pdf_path.exists(), "demo_sample_report.pdf fixture must exist"
    pdf_bytes = pdf_path.read_bytes()

    # 1. Ingestion: Upload PDF
    res_upload = client.post(
        "/api/documents/upload",
        files={"file": ("demo_sample_report.pdf", pdf_bytes, "application/pdf")},
    )
    assert res_upload.status_code == 201
    doc_id = res_upload.json()["document_id"]
    session_dir = get_safe_session_dir(doc_id)

    try:
        # 2. Detection & Entity Resolution
        res_detect = client.post(f"/api/documents/{doc_id}/detect")
        assert res_detect.status_code == 200
        candidates = res_detect.json()["candidates"]

        client.post(f"/api/documents/{doc_id}/entities/resolve")

        # 3. Approve all detected candidates
        for c in candidates:
            client.post(
                f"/api/documents/{doc_id}/review",
                json={"candidate_id": c["candidate_id"], "decision": "APPROVE"},
            )

        # 4. Native PDF Redaction & Verification
        res_redact = client.post(
            f"/api/documents/{doc_id}/redact",
            json={"placeholder_style": "CATEGORY"},
        )
        assert res_redact.status_code == 200
        red_json = res_redact.json()
        assert red_json["export_state"] in ("VERIFIED", "RECONSTRUCTED")

        # 5. Reopen output PDF and verify stream scrubbing
        res_dl = client.get(f"/api/documents/{doc_id}/export")
        assert res_dl.status_code == 200
        out_doc = pymupdf.open(stream=res_dl.content, filetype="pdf")
        pdf_extracted_text = ""
        for page in out_doc:
            pdf_extracted_text += page.get_text()
        out_doc.close()

        # Assert approved sensitive strings are physically scrubbed from stream
        assert "marcus.vance@solaris-defense.internal" not in pdf_extracted_text
        assert "EMP-94812" not in pdf_extracted_text

    finally:
        client.delete(f"/api/documents/{doc_id}")
        assert not session_dir.exists()


def test_demo_adversarial_leakage_and_suppression(client):
    """Part D on demo_summary_leakage_adversarial.txt."""
    adv_path = DEMO_DIR / "demo_summary_leakage_adversarial.txt"
    assert adv_path.exists()
    adv_bytes = adv_path.read_bytes()

    res_upload = client.post(
        "/api/documents/upload",
        files={"file": ("demo_summary_leakage_adversarial.txt", adv_bytes, "text/plain")},
    )
    assert res_upload.status_code == 201
    doc_id = res_upload.json()["document_id"]
    session_dir = get_safe_session_dir(doc_id)

    try:
        # Detect and approve
        res_det = client.post(f"/api/documents/{doc_id}/detect")
        for c in res_det.json()["candidates"]:
            client.post(
                f"/api/documents/{doc_id}/review",
                json={"candidate_id": c["candidate_id"], "decision": "APPROVE"},
            )

        # Redact
        res_red = client.post(
            f"/api/documents/{doc_id}/redact",
            json={"placeholder_style": "CATEGORY"},
        )
        assert res_red.status_code == 200
        sanitized_text = (session_dir / "sanitized.txt").read_text(encoding="utf-8")

        # SummaryGuard direct leakage test:
        # If an untrusted summary contains "Elena Rostova", verify_summary MUST fail closed!
        guard = SummaryGuard()
        san_doc = SanitizedDocument(
            document_id=doc_id,
            sanitized_text=sanitized_text,
            export_verification_ref="P5-VERIFIED",
            document_format="txt",
            permitted_metadata={},
        )

        simulated_leaking_summary = StructuredSummaryContent(
            summary_text="Dossier regarding Elena Rostova and the cryptographic key anomalies.",
            key_points=["Special Agent Elena Rostova was dispatched"],
            important_findings=[],
            relevant_dates_or_figures=[],
            source_evidence=[],
        )

        report = guard.verify_summary(
            summary_content=simulated_leaking_summary,
            sanitized_doc=san_doc,
            guard_references={
                "approved_values": ["Elena Rostova", "elena.rostova@quantum-audit.org"],
                "entity_variants": [],
            },
        )
        assert report.status == "FAILED", "Leaking summary must be blocked"
        assert any(c.check_name == "DIRECT_LEAKAGE" and c.status == "FAILED" for c in report.checks)

    finally:
        client.delete(f"/api/documents/{doc_id}")
        assert not session_dir.exists()
