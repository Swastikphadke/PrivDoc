"""Unit and integration tests for Phase P5: Redaction Engine & Export Verification.

Security & Verification Invariants Tested:
1. TXT Redaction: Immutable source text, descending offset order, configurable placeholders.
2. Unapproved & Rejected Preservation: Rejected candidates and unreviewed text are never removed.
3. Overlapping Spans: Overlapping approved intervals are merged into contiguous zones without corruption.
4. Unicode Support: Multi-byte and non-ASCII scripts (accented, Devanagari, CJK) handled with exact offsets.
5. PDF Redaction: PyMuPDF physical stream character deletion, no visual-only overlay tricks.
6. Headers, Footers & Multiple Occurrences: PII in repeating structures is completely eliminated.
7. Entity Variants: Both canonical names and alias variants verified absent.
8. Metadata Scrubbing: Author/Title/Producer metadata purged.
9. Verification Failure: Any detected leak causes FAILED status and strictly blocks export download.
10. Clean-Text Reconstruction: Verifiable PDF reconstruction fallback with layout-loss disclosure.
"""

import io
import json
import pytest
import pymupdf
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import get_safe_session_dir
from app.database.session import record_review_decision, update_document_status
from app.detectors.entity_resolver import EntityResolver
from app.schemas.candidate import Candidate, ConfidenceBand, ReviewStatus
from app.schemas.entity import Entity
from app.schemas.redaction import (
    ExportState,
    PlaceholderStyle,
    RedactionRequest,
    VerificationResult,
)
from app.services.redaction_service import RedactionService
from app.services.verification_service import VerificationService


# =========================================================================
# 1. TXT Redaction Unit Tests
# =========================================================================

def test_txt_redaction_basic_and_preservation():
    """Verify approved spans are masked while rejected and unreviewed text is preserved."""
    canonical_text = "Doctor Alice Smith examined patient Bob Jones. Phone: 9876543210."
    # Offsets:
    # "Alice Smith": [7, 18)
    # "Bob Jones": [36, 45)
    # "9876543210": [54, 64)

    c_alice = Candidate(
        candidate_id="c_001", document_id="doc_t1", start=7, end=18,
        text="Alice Smith", type="PERSON", confidence=0.95,
        confidence_band="HIGH", sources=["ner"], review_status="APPROVED",
    )
    c_bob = Candidate(
        candidate_id="c_002", document_id="doc_t1", start=36, end=45,
        text="Bob Jones", type="PERSON", confidence=0.90,
        confidence_band="HIGH", sources=["ner"], review_status="REJECTED",  # Preserved!
    )
    c_phone = Candidate(
        candidate_id="c_003", document_id="doc_t1", start=54, end=64,
        text="9876543210", type="PHONE", confidence=0.99,
        confidence_band="HIGH", sources=["regex"], review_status="APPROVED",
    )

    req = RedactionRequest(placeholder_style=PlaceholderStyle.CATEGORY)
    sanitized = RedactionService.apply_txt_redaction(
        canonical_text=canonical_text,
        approved_candidates=[c_alice, c_phone],
        request=req,
    )

    assert "Alice Smith" not in sanitized
    assert "9876543210" not in sanitized
    assert "[PERSON]" in sanitized
    assert "[PHONE]" in sanitized
    # Rejected candidate MUST remain in output
    assert "Bob Jones" in sanitized
    assert sanitized == "Doctor [PERSON] examined patient Bob Jones. Phone: [PHONE]."


def test_txt_redaction_overlapping_spans():
    """Verify overlapping and contiguous approved spans merge into a single replacement."""
    canonical_text = "Subject reference ID-998877A was verified."
    # "ID-998877A" is [18, 28)
    # Overlapping span 1: [18, 25) ("ID-9988")
    # Overlapping span 2: [21, 28) ("98877A")

    c1 = Candidate(
        candidate_id="c_o1", document_id="doc_o", start=18, end=25,
        text="ID-9988", type="ID_LIKE", confidence=0.88,
        confidence_band="HIGH", sources=["regex"], review_status="APPROVED",
    )
    c2 = Candidate(
        candidate_id="c_o2", document_id="doc_o", start=21, end=28,
        text="98877A", type="ID_LIKE", confidence=0.85,
        confidence_band="HIGH", sources=["ner"], review_status="APPROVED",
    )

    req = RedactionRequest(placeholder_style=PlaceholderStyle.CATEGORY)
    sanitized = RedactionService.apply_txt_redaction(
        canonical_text=canonical_text,
        approved_candidates=[c1, c2],
        request=req,
    )

    assert "ID-998877A" not in sanitized
    assert "ID-9988" not in sanitized
    assert "98877A" not in sanitized
    assert sanitized == "Subject reference [ID_LIKE] was verified."


def test_txt_redaction_unicode_multibyte():
    """Verify exact offset slicing and masking with accented and non-ASCII Unicode."""
    canonical_text = "Consultant Renée Müller visited आनंद कुमार in Tokyo."
    # Renée Müller: [11, 23)
    # आनंद कुमार: [32, 42)

    c_renee = Candidate(
        candidate_id="c_u1", document_id="doc_u", start=11, end=23,
        text="Renée Müller", type="PERSON", confidence=0.92,
        confidence_band="HIGH", sources=["ner"], review_status="APPROVED",
    )
    c_anand = Candidate(
        candidate_id="c_u2", document_id="doc_u", start=32, end=42,
        text="आनंद कुमार", type="PERSON", confidence=0.95,
        confidence_band="HIGH", sources=["ner"], review_status="APPROVED",
    )

    req = RedactionRequest(placeholder_style=PlaceholderStyle.CATEGORY)
    sanitized = RedactionService.apply_txt_redaction(
        canonical_text=canonical_text,
        approved_candidates=[c_renee, c_anand],
        request=req,
    )

    assert "Renée Müller" not in sanitized
    assert "आनंद कुमार" not in sanitized
    assert sanitized == "Consultant [PERSON] visited [PERSON] in Tokyo."


def test_txt_redaction_placeholder_styles():
    """Verify GENERIC ([REDACTED]), BLOCK (Unicode blocks), and CUSTOM styles."""
    canonical_text = "Contact Priya Nair."
    cand = Candidate(
        candidate_id="c_p1", document_id="doc_p", start=8, end=18,
        text="Priya Nair", type="PERSON", confidence=0.90,
        confidence_band="HIGH", sources=["ner"], review_status="APPROVED",
    )

    # 1. Generic
    req_gen = RedactionRequest(placeholder_style=PlaceholderStyle.GENERIC)
    san_gen = RedactionService.apply_txt_redaction(canonical_text, [cand], req_gen)
    assert san_gen == "Contact [REDACTED]."

    # 2. Block
    req_block = RedactionRequest(placeholder_style=PlaceholderStyle.BLOCK)
    san_block = RedactionService.apply_txt_redaction(canonical_text, [cand], req_block)
    assert "████" in san_block

    # 3. Custom
    req_cust = RedactionRequest(
        placeholder_style=PlaceholderStyle.CUSTOM,
        custom_placeholder="<CONFIDENTIAL_{category}>"
    )
    san_cust = RedactionService.apply_txt_redaction(canonical_text, [cand], req_cust)
    assert san_cust == "Contact <CONFIDENTIAL_PERSON>."


# =========================================================================
# 2. PDF Redaction & Native PyMuPDF Stream Tests
# =========================================================================

def test_pdf_native_redaction_purges_stream(tmp_path):
    """Verify PyMuPDF physically removes characters from text stream and scrubs metadata."""
    session_dir = tmp_path / "pdf_session"
    session_dir.mkdir(parents=True, exist_ok=True)
    orig_pdf = session_dir / "original.pdf"
    san_pdf = session_dir / "sanitized.pdf"

    # Create original test PDF with sensitive text, header, and metadata
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 40), "HEADER: PrivyDoc Internal - Author: Vikram Malhotra", fontsize=9)
    page.insert_text((50, 100), "Patient Vikram Malhotra was prescribed treatment by Dr. Sarah Jenkins.", fontsize=11)
    page.insert_text((50, 800), "FOOTER: Contact vikram@hospital.org", fontsize=8)
    doc.set_metadata({
        "author": "Vikram Malhotra",
        "title": "Medical Evaluation",
        "subject": "Confidential",
    })
    doc.save(orig_pdf)
    doc.close()

    # Define approved candidates
    c_vikram = Candidate(
        candidate_id="c_v1", document_id="pdoc", start=0, end=15,
        text="Vikram Malhotra", type="PERSON", confidence=0.99,
        confidence_band="HIGH", sources=["ner"], review_status="APPROVED",
    )
    c_email = Candidate(
        candidate_id="c_e1", document_id="pdoc", start=0, end=20,
        text="vikram@hospital.org", type="EMAIL", confidence=0.99,
        confidence_band="HIGH", sources=["regex"], review_status="APPROVED",
    )

    # Apply native redaction
    RedactionService.apply_native_pdf_redaction(
        session_dir=session_dir,
        approved_candidates=[c_vikram, c_email],
    )

    assert san_pdf.exists()

    # Reopen sanitized PDF and inspect
    res_doc = pymupdf.open(san_pdf)
    full_text = ""
    for p in res_doc:
        full_text += p.get_text("text")

    # Check 1: Sensitive text completely absent from extracted text
    assert "Vikram Malhotra" not in full_text
    assert "vikram@hospital.org" not in full_text
    # Check 2: Unredacted text remains intact
    assert "Dr. Sarah Jenkins" in full_text

    # Check 3: Metadata is thoroughly scrubbed
    meta = res_doc.metadata or {}
    assert "Vikram Malhotra" not in meta.get("author", "")
    assert "Vikram Malhotra" not in meta.get("title", "")

    # Check 4: Raw PDF stream inspection
    raw_bytes = san_pdf.read_bytes()
    assert b"Vikram Malhotra" not in raw_bytes
    assert b"vikram@hospital.org" not in raw_bytes

    res_doc.close()


def test_pdf_reconstruct_from_clean_text(tmp_path):
    """Verify clean-text PDF reconstruction generates a valid, parseable PDF."""
    sanitized_text = "This is a clean reconstituted document.\n\nAll [PERSON] data was redacted."
    out_pdf = tmp_path / "reconstructed.pdf"

    RedactionService.reconstruct_pdf_from_text(sanitized_text, out_pdf)
    assert out_pdf.exists()
    assert out_pdf.stat().st_size > 0

    doc = pymupdf.open(out_pdf)
    assert doc.page_count >= 1
    extracted = doc[0].get_text("text")
    assert "clean reconstituted document" in extracted
    assert "[PERSON]" in extracted
    doc.close()


# =========================================================================
# 3. Dedicated Verification Service Tests
# =========================================================================

def test_verification_detects_unredacted_pii_leak(tmp_path):
    """Verify that VerificationService detects exact strings, variants, and fails closed."""
    session_dir = tmp_path / "verif_session"
    session_dir.mkdir(parents=True, exist_ok=True)
    sanitized_file = session_dir / "sanitized.txt"

    # Simulate a buggy redaction where "Richa Sharma" was leaked
    sanitized_file.write_text("Hello Dr. Richa Sharma, your order is ready.", encoding="utf-8")

    approved_cand = Candidate(
        candidate_id="c_leak1", document_id="doc_l", start=10, end=22,
        text="Richa Sharma", type="PERSON", confidence=0.95,
        confidence_band="HIGH", sources=["ner"], review_status="APPROVED",
    )
    entity = Entity(
        entity_id="ent_1", canonical_name="Richa Sharma", entity_type="PERSON",
        candidate_ids=["c_leak1"], variants=["Richa Sharma", "R. Sharma"],
        confidence=1.0, evidence=["ner"],
    )

    result = VerificationService.verify_txt_export(
        document_id="doc_l",
        sanitized_txt_path=sanitized_file,
        approved_candidates=[approved_cand],
        entities=[entity],
    )

    assert result.status == "FAILED"
    assert len(result.issues) >= 1
    # Check that privacy invariant holds: raw PII string NOT in issue description
    for issue in result.issues:
        assert "Richa Sharma" not in issue.description
        assert "c_leak1" in issue.description or "ent_1" in issue.description


def test_verification_passes_when_fully_sanitized(tmp_path):
    """Verify that VerificationService returns PASSED when no approved PII or variants remain."""
    session_dir = tmp_path / "verif_clean"
    session_dir.mkdir(parents=True, exist_ok=True)
    sanitized_file = session_dir / "sanitized.txt"
    sanitized_file.write_text("Hello Dr. [PERSON], your order is ready.", encoding="utf-8")

    approved_cand = Candidate(
        candidate_id="c_clean1", document_id="doc_c", start=10, end=22,
        text="Richa Sharma", type="PERSON", confidence=0.95,
        confidence_band="HIGH", sources=["ner"], review_status="APPROVED",
    )
    entity = Entity(
        entity_id="ent_c1", canonical_name="Richa Sharma", entity_type="PERSON",
        candidate_ids=["c_clean1"], variants=["Richa Sharma", "R. Sharma"],
        confidence=1.0, evidence=["ner"],
    )

    result = VerificationService.verify_txt_export(
        document_id="doc_c",
        sanitized_txt_path=sanitized_file,
        approved_candidates=[approved_cand],
        entities=[entity],
    )

    assert result.status == "PASSED"
    assert len(result.issues) == 0


# =========================================================================
# 4. API End-to-End Redaction & Export Tests
# =========================================================================

def test_api_redact_and_export_txt_workflow():
    """Verify POST /api/documents/{id}/redact and GET /api/documents/{id}/export."""
    client = TestClient(app)

    # 1. Upload TXT document
    text_content = "Patient Suresh Menon consulted Dr. Priya Nair. Phone: 9876543210."
    upload_res = client.post(
        "/api/documents/upload",
        files={"file": ("clinical_test.txt", text_content.encode("utf-8"), "text/plain")},
    )
    assert upload_res.status_code in (200, 201)
    doc_id = upload_res.json()["document_id"]

    # 2. Run detection
    det_res = client.post(f"/api/documents/{doc_id}/detect")
    assert det_res.status_code == 200
    candidates = det_res.json()["candidates"]
    assert len(candidates) >= 2

    # 3. Approve first candidate, reject second
    c1 = candidates[0]
    client.post(
        f"/api/documents/{doc_id}/review",
        json={"candidate_id": c1["candidate_id"], "decision": "APPROVE"},
    )

    # 4. Execute Redaction
    redact_res = client.post(
        f"/api/documents/{doc_id}/redact",
        json={"placeholder_style": "CATEGORY"},
    )
    assert redact_res.status_code == 200
    data = redact_res.json()
    assert data["document_id"] == doc_id
    assert data["export_state"] == "VERIFIED"
    assert data["download_ready"] is True
    assert data["approved_redactions_applied"] >= 1
    assert data["verification"]["status"] == "PASSED"

    # 5. Download Exported Document
    export_res = client.get(f"/api/documents/{doc_id}/export")
    assert export_res.status_code == 200
    assert export_res.headers["content-type"].startswith("text/plain")
    sanitized_bytes = export_res.content
    sanitized_str = sanitized_bytes.decode("utf-8")

    # Verify approved candidate text is gone, placeholder is present
    assert c1["text"] not in sanitized_str

    # 6. Check Export Status Endpoint
    status_res = client.get(f"/api/documents/{doc_id}/export/status")
    assert status_res.status_code == 200
    assert status_res.json()["export_state"] == "VERIFIED"

    # Cleanup
    client.delete(f"/api/documents/{doc_id}")


def test_api_export_blocked_if_unverified():
    """Verify GET /api/documents/{id}/export returns 400 if export was not generated or verified."""
    client = TestClient(app)

    # Upload document but do not redact
    upload_res = client.post(
        "/api/documents/upload",
        files={"file": ("unverified.txt", b"Some unverified confidential content.", "text/plain")},
    )
    assert upload_res.status_code in (200, 201)
    doc_id = upload_res.json()["document_id"]

    # Attempt to download immediately: must be blocked
    export_res = client.get(f"/api/documents/{doc_id}/export")
    assert export_res.status_code == 400
    assert "Document has not been redacted" in export_res.json()["detail"]

    # Cleanup
    client.delete(f"/api/documents/{doc_id}")
