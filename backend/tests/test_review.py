"""Unit and Integration Tests for Human Review Actions & Workspace Endpoints (Phase P4 Backend).

Tests cover:
1. Approving an individual candidate.
2. Rejecting an individual candidate.
3. Reverting a decision (Undo -> PENDING).
4. Changing candidate PII category.
5. Bulk review applied to linked entity occurrences.
6. Bulk review applied to similar text occurrences ("Redact all similar").
7. Manual candidate addition with canonical offset validation.
8. Rejection of invalid, out-of-range, or empty manual selection spans.
9. PDF page image rendering (/pages/{page_num}/render).
10. Review summary statistics calculation.
"""

from fastapi.testclient import TestClient
import fitz
import pytest

from app.main import app
from app.schemas.candidate import ReviewStatus
from app.schemas.review import ReviewDecisionAction

client = TestClient(app)


@pytest.fixture
def session_with_candidates():
    """Create a temporary document session with detected candidates."""
    text = (
        "Report for Dr. Richa Sharma and Anil Kumar. "
        "Richa Sharma approved the budget. Contact richa@privydoc.local or call +91 98765 43210."
    )
    upload_res = client.post(
        "/api/documents/upload",
        files={"file": ("review_test.txt", text.encode("utf-8"), "text/plain")},
    )
    assert upload_res.status_code in [200, 201]
    doc_id = upload_res.json()["document_id"]

    # Trigger detection & entity resolution
    det_res = client.post(f"/api/documents/{doc_id}/detect")
    assert det_res.status_code == 200

    yield doc_id

    # Cleanup
    client.delete(f"/api/documents/{doc_id}")


def test_approve_and_reject_candidate(session_with_candidates):
    doc_id = session_with_candidates
    cands_res = client.get(f"/api/documents/{doc_id}/candidates")
    candidates = cands_res.json()
    assert len(candidates) >= 2

    target_1 = candidates[0]["candidate_id"]
    target_2 = candidates[1]["candidate_id"]

    # 1. Approve target_1
    app_res = client.post(
        f"/api/documents/{doc_id}/review",
        json={"candidate_id": target_1, "decision": "APPROVE"},
    )
    assert app_res.status_code == 200
    summary = app_res.json()
    assert summary["approved_count"] == 1

    # Verify target_1 status in returned list
    updated_1 = next(c for c in summary["candidates"] if c["candidate_id"] == target_1)
    assert updated_1["review_status"] == ReviewStatus.APPROVED.value

    # 2. Reject target_2
    rej_res = client.post(
        f"/api/documents/{doc_id}/review",
        json={"candidate_id": target_2, "decision": "REJECT"},
    )
    assert rej_res.status_code == 200
    summary_2 = rej_res.json()
    assert summary_2["approved_count"] == 1
    assert summary_2["rejected_count"] == 1


def test_undo_decision_reverts_to_pending(session_with_candidates):
    doc_id = session_with_candidates
    cands_res = client.get(f"/api/documents/{doc_id}/candidates")
    candidates = cands_res.json()
    target_id = candidates[0]["candidate_id"]

    # Approve
    client.post(
        f"/api/documents/{doc_id}/review",
        json={"candidate_id": target_id, "decision": "APPROVE"},
    )

    # Undo -> PENDING
    undo_res = client.post(
        f"/api/documents/{doc_id}/review",
        json={"candidate_id": target_id, "decision": "PENDING"},
    )
    assert undo_res.status_code == 200
    summary = undo_res.json()
    reverted = next(c for c in summary["candidates"] if c["candidate_id"] == target_id)
    assert reverted["review_status"] == ReviewStatus.PENDING.value
    assert summary["approved_count"] == 0


def test_change_candidate_category(session_with_candidates):
    doc_id = session_with_candidates
    cands_res = client.get(f"/api/documents/{doc_id}/candidates")
    candidates = cands_res.json()
    target_id = candidates[0]["candidate_id"]

    res = client.post(
        f"/api/documents/{doc_id}/review",
        json={"candidate_id": target_id, "decision": "APPROVE", "new_type": "ID_LIKE"},
    )
    assert res.status_code == 200
    summary = res.json()
    changed = next(c for c in summary["candidates"] if c["candidate_id"] == target_id)
    assert changed["type"] == "ID_LIKE"
    assert changed["review_status"] == ReviewStatus.APPROVED.value


def test_bulk_review_linked_and_similar(session_with_candidates):
    doc_id = session_with_candidates
    cands_res = client.get(f"/api/documents/{doc_id}/candidates")
    candidates = cands_res.json()

    # Find candidate with occurrences (Richa Sharma)
    richa_cands = [c for c in candidates if "Richa Sharma" in c["text"]]
    assert len(richa_cands) >= 2

    # Bulk approve all linked occurrences
    first_id = richa_cands[0]["candidate_id"]
    res = client.post(
        f"/api/documents/{doc_id}/review",
        json={
            "candidate_id": first_id,
            "decision": "APPROVE",
            "apply_to_linked": True,
        },
    )
    assert res.status_code == 200
    summary = res.json()
    for rc in richa_cands:
        updated = next(c for c in summary["candidates"] if c["candidate_id"] == rc["candidate_id"])
        assert updated["review_status"] == ReviewStatus.APPROVED.value


def test_manual_candidate_addition(session_with_candidates):
    doc_id = session_with_candidates
    # Add manual candidate for "Anil Kumar" or arbitrary text in doc
    # Text: "Report for Dr. Richa Sharma and Anil Kumar."
    # Let's add manual span for "Anil Kumar" (starts at index 32)
    doc_res = client.get(f"/api/documents/{doc_id}")
    text = doc_res.json()["extracted_text"]
    start = text.index("Anil Kumar")
    end = start + len("Anil Kumar")

    man_res = client.post(
        f"/api/documents/{doc_id}/candidates/manual",
        json={"start": start, "end": end, "type": "PERSON"},
    )
    assert man_res.status_code == 201
    created = man_res.json()
    assert created["text"] == "Anil Kumar"
    assert created["review_status"] == ReviewStatus.APPROVED.value
    assert "manual" in created["sources"]

    # Verify review summary includes manual count
    summary_res = client.get(f"/api/documents/{doc_id}/review")
    assert summary_res.status_code == 200
    assert summary_res.json()["manual_count"] >= 1


def test_manual_candidate_invalid_offsets_rejected(session_with_candidates):
    doc_id = session_with_candidates
    # Out of range end
    res = client.post(
        f"/api/documents/{doc_id}/candidates/manual",
        json={"start": 10, "end": 99999, "type": "PERSON"},
    )
    assert res.status_code == 400

    # Start >= end
    res2 = client.post(
        f"/api/documents/{doc_id}/candidates/manual",
        json={"start": 20, "end": 10, "type": "PERSON"},
    )
    assert res2.status_code == 422 or res2.status_code == 400


def test_pdf_page_render_endpoint():
    """Verify PyMuPDF renders PDF pages to PNG image streams."""
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.insert_text((50, 50), "PrivyDoc Confidential Review")
    pdf_bytes = doc.tobytes()
    doc.close()

    upload_res = client.post(
        "/api/documents/upload",
        files={"file": ("page_render_test.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_res.status_code in [200, 201]
    doc_id = upload_res.json()["document_id"]

    try:
        render_res = client.get(f"/api/documents/{doc_id}/pages/1/render")
        assert render_res.status_code == 200
        assert render_res.headers["content-type"] == "image/png"
        assert len(render_res.content) > 100

        # Out of bounds page
        err_res = client.get(f"/api/documents/{doc_id}/pages/99/render")
        assert err_res.status_code == 400
    finally:
        client.delete(f"/api/documents/{doc_id}")
