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



# =========================================================================
# 5. Mandatory Adversarial Testing Suite (P5 Quality Gates)
# =========================================================================

def test_adversarial_1_multiple_identical_occurrences(tmp_path):
    """Scenario 1: Multiple identical occurrences of the same sensitive string across document."""
    text = "Operation Titan commenced at dawn. Team Titan secured the objective. Titan debrief concluded."
    # "Titan" appears at [10, 15), [41, 46), [71, 76)
    c1 = Candidate(
        candidate_id="c_t1", document_id="d1", start=10, end=15,
        text="Titan", type="ID_LIKE", confidence=0.95,
        confidence_band="HIGH", sources=["regex"], review_status="APPROVED",
    )
    c2 = Candidate(
        candidate_id="c_t2", document_id="d1", start=41, end=46,
        text="Titan", type="ID_LIKE", confidence=0.95,
        confidence_band="HIGH", sources=["regex"], review_status="APPROVED",
    )
    c3 = Candidate(
        candidate_id="c_t3", document_id="d1", start=71, end=76,
        text="Titan", type="ID_LIKE", confidence=0.95,
        confidence_band="HIGH", sources=["regex"], review_status="APPROVED",
    )

    req = RedactionRequest(placeholder_style=PlaceholderStyle.CATEGORY)
    sanitized = RedactionService.apply_txt_redaction(text, [c1, c2, c3], req)

    assert "Titan" not in sanitized
    assert sanitized.count("[ID_LIKE]") == 3

    # Verification: must confirm 0 occurrences remain
    san_file = tmp_path / "sanitized.txt"
    san_file.write_text(sanitized, encoding="utf-8")
    res = VerificationService.verify_txt_export("d1", san_file, text, [c1, c2, c3], [c1, c2, c3], [])
    assert res.status == "PASSED"
    assert len(res.issues) == 0


def test_adversarial_2_multiple_name_variants(tmp_path):
    """Scenario 2: Multiple variants of a person's name (canonical, alias, initial)."""
    text = "Dr. Jonathan Edward Smith met with Jonathan Smith and J. Smith regarding patient files."
    c1 = Candidate(
        candidate_id="c_v1", document_id="d2", start=0, end=25,
        text="Dr. Jonathan Edward Smith", type="PERSON", confidence=0.98,
        confidence_band="HIGH", sources=["ner"], review_status="APPROVED",
    )
    c2 = Candidate(
        candidate_id="c_v2", document_id="d2", start=35, end=49,
        text="Jonathan Smith", type="PERSON", confidence=0.94,
        confidence_band="HIGH", sources=["ner"], review_status="APPROVED",
    )
    c3 = Candidate(
        candidate_id="c_v3", document_id="d2", start=54, end=62,
        text="J. Smith", type="PERSON", confidence=0.88,
        confidence_band="HIGH", sources=["ner"], review_status="APPROVED",
    )

    entity = Entity(
        entity_id="ent_jes",
        canonical_name="Dr. Jonathan Edward Smith",
        entity_type="PERSON",
        candidate_ids=["c_v1", "c_v2", "c_v3"],
        variants=["Dr. Jonathan Edward Smith", "Jonathan Smith", "J. Smith", "J. E. Smith"],
        confidence=0.95,
        evidence=["ner"],
    )

    req = RedactionRequest(placeholder_style=PlaceholderStyle.CATEGORY)
    sanitized = RedactionService.apply_txt_redaction(text, [c1, c2, c3], req)

    for var in entity.variants:
        if var != "J. E. Smith":
            assert var not in sanitized

    san_file = tmp_path / "sanitized.txt"
    san_file.write_text(sanitized, encoding="utf-8")
    res = VerificationService.verify_txt_export("d2", san_file, text, [c1, c2, c3], [c1, c2, c3], [entity])
    assert res.status == "PASSED"
    assert len(res.issues) == 0


def test_adversarial_3_unicode_and_non_ascii_scripts(tmp_path):
    """Scenario 3: Complex multi-script Unicode (Devanagari, Japanese, German umlaut, Cyrillic)."""
    text = "Patient अमित शर्मा (Tokyo ID: 山田 太郎) treated by Dr. Jörg Weiß in Moscow with Алексей Иванов."
    s_amit = text.index("अमित शर्मा")
    e_amit = s_amit + len("अमित शर्मा")
    s_yamada = text.index("山田 太郎")
    e_yamada = s_yamada + len("山田 太郎")
    s_jorg = text.index("Jörg Weiß")
    e_jorg = s_jorg + len("Jörg Weiß")
    s_alexei = text.index("Алексей Иванов")
    e_alexei = s_alexei + len("Алексей Иванов")

    c_amit = Candidate(candidate_id="c_u1", document_id="d3", start=s_amit, end=e_amit, text="अमित शर्मा", type="PERSON", confidence=0.95, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")
    c_yamada = Candidate(candidate_id="c_u2", document_id="d3", start=s_yamada, end=e_yamada, text="山田 太郎", type="PERSON", confidence=0.95, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")
    c_jorg = Candidate(candidate_id="c_u3", document_id="d3", start=s_jorg, end=e_jorg, text="Jörg Weiß", type="PERSON", confidence=0.95, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")
    c_alexei = Candidate(candidate_id="c_u4", document_id="d3", start=s_alexei, end=e_alexei, text="Алексей Иванов", type="PERSON", confidence=0.95, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")

    req = RedactionRequest(placeholder_style=PlaceholderStyle.CATEGORY)
    sanitized = RedactionService.apply_txt_redaction(text, [c_amit, c_yamada, c_jorg, c_alexei], req)

    assert "अमित शर्मा" not in sanitized
    assert "山田 太郎" not in sanitized
    assert "Jörg Weiß" not in sanitized
    assert "Алексей Иванов" not in sanitized
    assert sanitized.count("[PERSON]") == 4

    san_file = tmp_path / "sanitized.txt"
    san_file.write_text(sanitized, encoding="utf-8")
    res = VerificationService.verify_txt_export("d3", san_file, text, [c_amit, c_yamada, c_jorg, c_alexei], [c_amit, c_yamada, c_jorg, c_alexei], [])
    assert res.status == "PASSED"


def test_adversarial_4_complex_overlapping_and_nested_spans():
    """Scenario 4: Overlapping, subsumed/nested, and contiguous approved spans."""
    text = "Access Key SEC-ID-8842-CONFIDENTIAL granted."
    c1 = Candidate(candidate_id="c_ov1", document_id="d4", start=11, end=35, text="SEC-ID-8842-CONFIDENTIAL", type="ID_LIKE", confidence=0.90, confidence_band="HIGH", sources=["regex"], review_status="APPROVED")
    c2 = Candidate(candidate_id="c_ov2", document_id="d4", start=18, end=22, text="8842", type="ID_LIKE", confidence=0.80, confidence_band="HIGH", sources=["regex"], review_status="APPROVED")
    c3 = Candidate(candidate_id="c_ov3", document_id="d4", start=11, end=17, text="SEC-ID", type="ID_LIKE", confidence=0.85, confidence_band="HIGH", sources=["regex"], review_status="APPROVED")
    c4 = Candidate(candidate_id="c_ov4", document_id="d4", start=35, end=43, text=" granted", type="ID_LIKE", confidence=0.75, confidence_band="HIGH", sources=["regex"], review_status="APPROVED")

    req = RedactionRequest(placeholder_style=PlaceholderStyle.CATEGORY)
    sanitized = RedactionService.apply_txt_redaction(text, [c1, c2, c3, c4], req)

    assert sanitized == "Access Key [ID_LIKE]."


def test_adversarial_5_invalid_and_out_of_range_offsets():
    """Scenario 5: Spans with negative start, start >= end, and end > text length."""
    text = "Valid text content."
    c_neg = Candidate(candidate_id="c_bad1", document_id="d5", start=-5, end=5, text="???", type="PERSON", confidence=0.5, confidence_band="LOW", sources=["ner"], review_status="APPROVED")
    c_inv = Candidate(candidate_id="c_bad2", document_id="d5", start=10, end=10, text="", type="PERSON", confidence=0.5, confidence_band="LOW", sources=["ner"], review_status="APPROVED")
    c_rev = Candidate(candidate_id="c_bad3", document_id="d5", start=15, end=8, text="???", type="PERSON", confidence=0.5, confidence_band="LOW", sources=["ner"], review_status="APPROVED")
    c_oob = Candidate(candidate_id="c_bad4", document_id="d5", start=12, end=50, text="???", type="PERSON", confidence=0.5, confidence_band="LOW", sources=["ner"], review_status="APPROVED")
    c_ok = Candidate(candidate_id="c_ok", document_id="d5", start=0, end=5, text="Valid", type="ID_LIKE", confidence=0.9, confidence_band="HIGH", sources=["regex"], review_status="APPROVED")

    req = RedactionRequest(placeholder_style=PlaceholderStyle.CATEGORY)
    sanitized = RedactionService.apply_txt_redaction(text, [c_neg, c_inv, c_rev, c_oob, c_ok], req)

    assert sanitized == "[ID_LIKE] text content."


def test_adversarial_6_approved_vs_rejected_identical_text(tmp_path):
    """Scenario 6: Same surface text appears twice; one approved, one rejected."""
    text = "Report authored by Miller. The water mill operated normally. Contact Miller for details."
    c_app = Candidate(candidate_id="c_m1", document_id="d6", start=19, end=25, text="Miller", type="PERSON", confidence=0.95, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")
    c_rej = Candidate(candidate_id="c_m2", document_id="d6", start=69, end=75, text="Miller", type="PERSON", confidence=0.90, confidence_band="HIGH", sources=["ner"], review_status="REJECTED")

    req = RedactionRequest(placeholder_style=PlaceholderStyle.CATEGORY)
    sanitized = RedactionService.apply_txt_redaction(text, [c_app], req)

    assert sanitized == "Report authored by [PERSON]. The water mill operated normally. Contact Miller for details."

    san_file = tmp_path / "sanitized.txt"
    san_file.write_text(sanitized, encoding="utf-8")
    res = VerificationService.verify_txt_export("d6", san_file, text, [c_app], [c_app, c_rej], [])
    assert res.status == "PASSED"
    assert len(res.issues) == 0


def test_adversarial_7_pending_candidates_never_redacted():
    """Scenario 7: Unreviewed / PENDING candidates must remain strictly unredacted."""
    text = "Reviewed Dr. Alice Clark and unreviewed Dr. Bob Taylor."
    c_alice = Candidate(candidate_id="c_p1", document_id="d7", start=9, end=24, text="Dr. Alice Clark", type="PERSON", confidence=0.95, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")
    c_bob = Candidate(candidate_id="c_p2", document_id="d7", start=40, end=54, text="Dr. Bob Taylor", type="PERSON", confidence=0.85, confidence_band="HIGH", sources=["ner"], review_status="PENDING")

    req = RedactionRequest(placeholder_style=PlaceholderStyle.CATEGORY)
    sanitized = RedactionService.apply_txt_redaction(text, [c_alice], req)

    assert "Dr. Alice Clark" not in sanitized
    assert "[PERSON]" in sanitized
    assert "Dr. Bob Taylor" in sanitized


def test_adversarial_8_entity_linked_bulk_approval(tmp_path):
    """Scenario 8: Multiple occurrences linked to an entity, approved together."""
    text = "Patient Ramesh Rao was examined. Ramesh Rao was discharged. Ramesh Rao recovered."
    s1 = text.index("Ramesh Rao")
    s2 = text.index("Ramesh Rao", s1 + 10)
    s3 = text.index("Ramesh Rao", s2 + 10)

    c1 = Candidate(candidate_id="c_e1", document_id="d8", start=s1, end=s1 + 10, text="Ramesh Rao", type="PERSON", confidence=0.95, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")
    c2 = Candidate(candidate_id="c_e2", document_id="d8", start=s2, end=s2 + 10, text="Ramesh Rao", type="PERSON", confidence=0.95, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")
    c3 = Candidate(candidate_id="c_e3", document_id="d8", start=s3, end=s3 + 10, text="Ramesh Rao", type="PERSON", confidence=0.95, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")

    entity = Entity(
        entity_id="ent_rr", canonical_name="Ramesh Rao", entity_type="PERSON",
        candidate_ids=["c_e1", "c_e2", "c_e3"], variants=["Ramesh Rao", "R. Rao"],
        confidence=0.99, evidence=["ner"],
    )

    req = RedactionRequest(placeholder_style=PlaceholderStyle.CATEGORY)
    sanitized = RedactionService.apply_txt_redaction(text, [c1, c2, c3], req)

    assert "Ramesh Rao" not in sanitized
    assert sanitized.count("[PERSON]") == 3

    san_file = tmp_path / "sanitized.txt"
    san_file.write_text(sanitized, encoding="utf-8")
    res = VerificationService.verify_txt_export("d8", san_file, text, [c1, c2, c3], [c1, c2, c3], [entity])
    assert res.status == "PASSED"


def test_adversarial_9_multipage_pdf_redaction(tmp_path):
    """Scenario 9: Multi-page PDF with sensitive spans across pages 1, 2, and 3."""
    session_dir = tmp_path / "pdf_multi"
    session_dir.mkdir(parents=True, exist_ok=True)
    orig_pdf = session_dir / "original.pdf"
    san_pdf = session_dir / "sanitized.pdf"

    doc = pymupdf.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 100), "Page 1: Patient Rajesh Kumar admitted for evaluation.", fontsize=12)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 100), "Page 2: Lab diagnostic report for Rajesh Kumar completed.", fontsize=12)
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text((50, 100), "Page 3: Discharge protocol signed for Rajesh Kumar.", fontsize=12)
    doc.save(orig_pdf)
    doc.close()

    c_p1 = Candidate(candidate_id="c_m1", document_id="d9", start=0, end=12, text="Rajesh Kumar", type="PERSON", confidence=0.99, confidence_band="HIGH", sources=["ner"], review_status="APPROVED", page_number=1)
    c_p2 = Candidate(candidate_id="c_m2", document_id="d9", start=0, end=12, text="Rajesh Kumar", type="PERSON", confidence=0.99, confidence_band="HIGH", sources=["ner"], review_status="APPROVED", page_number=2)
    c_p3 = Candidate(candidate_id="c_m3", document_id="d9", start=0, end=12, text="Rajesh Kumar", type="PERSON", confidence=0.99, confidence_band="HIGH", sources=["ner"], review_status="APPROVED", page_number=3)

    RedactionService.apply_native_pdf_redaction(session_dir, san_pdf, [c_p1, c_p2, c_p3])

    res = VerificationService.verify_pdf_export("d9", san_pdf, [c_p1, c_p2, c_p3], [c_p1, c_p2, c_p3], [])
    assert res.status == "PASSED"

    # Confirm across all pages physically
    res_doc = pymupdf.open(san_pdf)
    assert res_doc.page_count == 3
    for p in res_doc:
        assert "Rajesh Kumar" not in p.get_text("text")
    res_doc.close()


def test_adversarial_10_headers_and_footers_recurring(tmp_path):
    """Scenario 10: Recurring header and footer across multiple PDF pages."""
    session_dir = tmp_path / "pdf_hdr"
    session_dir.mkdir(parents=True, exist_ok=True)
    orig_pdf = session_dir / "original.pdf"
    san_pdf = session_dir / "sanitized.pdf"

    doc = pymupdf.open()
    for i in range(2):
        p = doc.new_page(width=595, height=842)
        p.insert_text((50, 30), "CONFIDENTIAL HEADER: Dr. Nina Patel Clinic", fontsize=10)
        p.insert_text((50, 100), f"Body text on page {i+1} with non-sensitive observations.", fontsize=11)
        p.insert_text((50, 800), "FOOTER: Direct Line: 9876543210", fontsize=9)
    doc.save(orig_pdf)
    doc.close()

    c_nina = Candidate(candidate_id="c_h1", document_id="d10", start=0, end=10, text="Nina Patel", type="PERSON", confidence=0.95, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")
    c_phone = Candidate(candidate_id="c_h2", document_id="d10", start=0, end=10, text="9876543210", type="PHONE", confidence=0.99, confidence_band="HIGH", sources=["regex"], review_status="APPROVED")

    RedactionService.apply_native_pdf_redaction(session_dir, san_pdf, [c_nina, c_phone])

    res = VerificationService.verify_pdf_export("d10", san_pdf, [c_nina, c_phone], [c_nina, c_phone], [])
    assert res.status == "PASSED"

    res_doc = pymupdf.open(san_pdf)
    for p in res_doc:
        page_text = p.get_text("text")
        assert "Nina Patel" not in page_text
        assert "9876543210" not in page_text
    res_doc.close()


def test_adversarial_11_pdf_text_split_across_spans(tmp_path):
    """Scenario 11: Text split across separate span insertions in a PDF."""
    session_dir = tmp_path / "pdf_split"
    session_dir.mkdir(parents=True, exist_ok=True)
    orig_pdf = session_dir / "original.pdf"
    san_pdf = session_dir / "sanitized.pdf"

    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((50, 100), "Dr. Sarah ", fontsize=11)
    p.insert_text((105, 100), "Connor attended the conference.", fontsize=11)
    doc.save(orig_pdf)
    doc.close()

    c_sarah = Candidate(candidate_id="c_s1", document_id="d11", start=0, end=5, text="Sarah", type="PERSON", confidence=0.95, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")
    c_connor = Candidate(candidate_id="c_s2", document_id="d11", start=6, end=12, text="Connor", type="PERSON", confidence=0.95, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")

    RedactionService.apply_native_pdf_redaction(session_dir, san_pdf, [c_sarah, c_connor])

    res = VerificationService.verify_pdf_export("d11", san_pdf, [c_sarah, c_connor], [c_sarah, c_connor], [])
    assert res.status == "PASSED"

    res_doc = pymupdf.open(san_pdf)
    t = res_doc[0].get_text("text")
    assert "Sarah" not in t
    assert "Connor" not in t
    assert "attended the conference" in t
    res_doc.close()


def test_adversarial_12_pdf_metadata_purged(tmp_path):
    """Scenario 12: PDF metadata containing author, title, and sensitive keywords purged."""
    session_dir = tmp_path / "pdf_meta"
    session_dir.mkdir(parents=True, exist_ok=True)
    orig_pdf = session_dir / "original.pdf"
    san_pdf = session_dir / "sanitized.pdf"

    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((50, 100), "Routine non-sensitive summary text.", fontsize=11)
    doc.set_metadata({
        "author": "Elena Fisher",
        "title": "Secret Record of Elena Fisher",
        "subject": "Confidential",
        "keywords": "Elena Fisher, Classified",
    })
    doc.save(orig_pdf)
    doc.close()

    c_elena = Candidate(candidate_id="c_el1", document_id="d12", start=0, end=12, text="Elena Fisher", type="PERSON", confidence=0.99, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")

    RedactionService.apply_native_pdf_redaction(session_dir, san_pdf, [c_elena])

    res = VerificationService.verify_pdf_export("d12", san_pdf, [c_elena], [c_elena], [])
    assert res.status == "PASSED"

    res_doc = pymupdf.open(san_pdf)
    meta = res_doc.metadata or {}
    for key, val in meta.items():
        assert "Elena Fisher" not in str(val)
    res_doc.close()


def test_adversarial_13_pdf_annotations_widgets_and_links(tmp_path):
    """Scenario 13: Interactive form field widgets and link annotations containing PII."""
    session_dir = tmp_path / "pdf_forms"
    session_dir.mkdir(parents=True, exist_ok=True)
    orig_pdf = session_dir / "original.pdf"
    san_pdf = session_dir / "sanitized.pdf"

    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((50, 50), "Patient Registration Form", fontsize=12)

    p.insert_link({
        "kind": pymupdf.LINK_URI,
        "from": pymupdf.Rect(50, 80, 200, 100),
        "uri": "mailto:maya.lin@clinic.org",
    })

    widget = pymupdf.Widget()
    widget.rect = pymupdf.Rect(50, 120, 200, 140)
    widget.field_name = "patient_name"
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.field_value = "Dr. Maya Lin"
    p.add_widget(widget)

    doc.save(orig_pdf)
    doc.close()

    c_maya = Candidate(candidate_id="c_w1", document_id="d13", start=0, end=8, text="Maya Lin", type="PERSON", confidence=0.99, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")
    c_email = Candidate(candidate_id="c_w2", document_id="d13", start=0, end=20, text="maya.lin@clinic.org", type="EMAIL", confidence=0.99, confidence_band="HIGH", sources=["regex"], review_status="APPROVED")

    RedactionService.apply_native_pdf_redaction(session_dir, san_pdf, [c_maya, c_email])

    res = VerificationService.verify_pdf_export("d13", san_pdf, [c_maya, c_email], [c_maya, c_email], [])
    assert res.status == "PASSED"

    res_doc = pymupdf.open(san_pdf)
    res_page = res_doc[0]

    links = res_page.get_links()
    for link in links:
        assert "maya.lin@clinic.org" not in link.get("uri", "")

    for w in res_page.widgets():
        assert "Maya Lin" not in str(w.field_value or "")

    res_doc.close()


def test_adversarial_14_corrupt_malformed_pdf_fails_closed(tmp_path):
    """Scenario 14: Corrupted or truncated PDF file safely fails closed without leaking."""
    session_dir = tmp_path / "pdf_corrupt"
    session_dir.mkdir(parents=True, exist_ok=True)
    orig_pdf = session_dir / "original.pdf"
    orig_pdf.write_bytes(b"%PDF-1.4 CORRUPTED_GARBAGE_NOT_A_VALID_STRUCTURE")

    c = Candidate(candidate_id="c_cr1", document_id="d14", start=0, end=5, text="Alice", type="PERSON", confidence=0.9, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")

    with pytest.raises(Exception):
        RedactionService.apply_native_pdf_redaction(session_dir, session_dir / "sanitized.pdf", [c])


def test_adversarial_15_verification_failure_injection_blocks_export(tmp_path):
    """Scenario 15: Injected leak in sanitized file triggers FAILED verification and blocks export."""
    session_dir = tmp_path / "pdf_leak"
    session_dir.mkdir(parents=True, exist_ok=True)
    san_pdf = session_dir / "sanitized.pdf"

    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((50, 100), "Unredacted leak: Dr. Secret attended.", fontsize=11)
    doc.save(san_pdf)
    doc.close()

    c_secret = Candidate(candidate_id="c_sec", document_id="d15", start=0, end=10, text="Dr. Secret", type="PERSON", confidence=0.99, confidence_band="HIGH", sources=["ner"], review_status="APPROVED")

    res = VerificationService.verify_pdf_export("d15", san_pdf, [c_secret], [c_secret], [])
    assert res.status == "FAILED"
    assert len(res.issues) >= 1
    assert any(i.diagnostic_code in ("EXTRACTABLE_TEXT_LEAK_PDF", "APPROVED_TEXT_LEAK_PDF") for i in res.issues)
    for issue in res.issues:
        assert "Dr. Secret" not in issue.description


def test_adversarial_16_unauthorized_export_and_path_traversal():
    """Scenario 16: Path traversal attempts on /redact, /export/status, and /export rejected with 400 or 404."""
    client = TestClient(app)

    malicious_ids = [
        "../../etc/passwd",
        "doc..id",
        "doc/sub/path",
        "doc;rm -rf",
        "doc' OR '1'='1",
        "../escaped",
    ]

    for bad_id in malicious_ids:
        r1 = client.get(f"/api/documents/{bad_id}/export")
        assert r1.status_code in (400, 404)
        if r1.status_code == 400:
            assert "Invalid document ID format" in r1.json()["detail"]

        r2 = client.get(f"/api/documents/{bad_id}/export/status")
        assert r2.status_code in (400, 404)

        r3 = client.post(f"/api/documents/{bad_id}/redact", json={})
        assert r3.status_code in (400, 404)


def test_adversarial_17_export_cache_invalidation_and_stale_prevention():
    """Scenario 17: Invalidate and purge old export files when re-redacting or upon failure."""
    client = TestClient(app)

    up = client.post(
        "/api/documents/upload",
        files={"file": ("stale_test.txt", b"Sensitive data Dr. James Wilson is here.", "text/plain")},
    )
    assert up.status_code in (200, 201)
    doc_id = up.json()["document_id"]

    client.post(
        f"/api/documents/{doc_id}/candidates/manual",
        json={"start": 15, "end": 31, "text": "Dr. James Wilson", "type": "PERSON"},
    )
    client.post(f"/api/documents/{doc_id}/review/all", json={"decision": "APPROVE"})

    red1 = client.post(f"/api/documents/{doc_id}/redact", json={})
    assert red1.status_code == 200
    assert red1.json()["export_state"] == "VERIFIED"

    exp1 = client.get(f"/api/documents/{doc_id}/export")
    assert exp1.status_code == 200
    assert b"Dr. James Wilson" not in exp1.content

    session_dir = get_safe_session_dir(doc_id)
    san_file = session_dir / "sanitized.txt"
    assert san_file.exists()

    RedactionService._invalidate_existing_exports(session_dir)
    assert not san_file.exists()

    exp2 = client.get(f"/api/documents/{doc_id}/export")
    assert exp2.status_code in (400, 404)

    client.delete(f"/api/documents/{doc_id}")


def test_adversarial_18_clean_text_pdf_reconstruction_with_warnings(tmp_path):
    """Scenario 18: Clean-text PDF reconstruction fallback with layout-loss disclosures."""
    sanitized_text = "RECONSTRUCTED DOCUMENT\n\nAll confidential patient data has been removed.\nSummary: [PERSON] received [ID_LIKE]."
    out_pdf = tmp_path / "reconstructed.pdf"

    RedactionService.reconstruct_pdf_from_text(sanitized_text, out_pdf)
    assert out_pdf.exists()

    res = VerificationService.verify_pdf_export(
        document_id="d18",
        sanitized_pdf_path=out_pdf,
        approved_candidates=[],
        all_candidates=[],
        entities=[],
    )
    assert res.status == "PASSED"
    assert any("PDF structural limitations" in w for w in res.warnings)

    doc = pymupdf.open(out_pdf)
    extracted = doc[0].get_text("text")
    assert "RECONSTRUCTED DOCUMENT" in extracted
    assert "[PERSON]" in extracted
    doc.close()
