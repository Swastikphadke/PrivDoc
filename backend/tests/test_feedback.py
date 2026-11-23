"""Unit and Privacy Tests for Local Feedback System and Opt-In Alias Encryption.

Strict Privacy & Integrity Invariants Tested:
1. Data Minimization: SQLite feedback_records contains ZERO raw document text, ZERO snippets,
   and ZERO raw candidate PII strings.
2. Consent Gate: Storing name variant aliases STRICTLY requires explicit opt-in (opt_in_consent=True).
   Silent retention is blocked with an error.
3. Authenticated Encryption: Opt-in aliases are encrypted using local AES-256-GCM with expiration tags.
4. Cascade Deletion: Purging a document session removes all feedback and encrypted aliases.
5. Controlled Proposals: Feedback analysis aggregates rejections and generates read-only PROPOSED rules;
   NEVER auto-mutates detection regexes or SLM parameters at runtime.
"""

import json
import sqlite3
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.core.config import settings
from app.database.session import (
    get_db_connection,
    init_db,
    save_document_metadata,
    delete_document_record,
    get_feedback_records,
)
from app.main import app
from app.schemas.candidate import Candidate
from app.schemas.feedback import FeedbackAction, OptInAliasRequest
from app.services.feedback_service import FeedbackService
from app.detectors.regex_detector import RegexDetector


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM opt_in_encrypted_aliases")
        cursor.execute("DELETE FROM feedback_records")
        conn.commit()
    yield
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM opt_in_encrypted_aliases")
        cursor.execute("DELETE FROM feedback_records")
        conn.commit()


def test_data_minimization_invariant():
    """Verify that feedback_records table schema and rows contain NO raw text columns or PII."""
    doc_id = "doc_privacy_test"
    save_document_metadata(doc_id, "contract.txt", "txt", "INGESTED", 1, 100)

    cand = Candidate(
        candidate_id="c_secret_1",
        document_id=doc_id,
        start=10,
        end=25,
        text="SuperSecretName",  # Sensitive PII
        type="PERSON",
        confidence=0.95,
        sources=["ner_detector"],
    )

    # Record rejection feedback
    fb_id = FeedbackService.record_review_feedback(
        document_id=doc_id,
        candidate=cand,
        action="REJECTED",
        scope="OCCURRENCE",
    )

    # Directly inspect SQLite rows and column names
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM feedback_records WHERE id = ?", (fb_id,))
        row = dict(cursor.fetchone())
        
        # Verify column names do NOT include text, raw_text, snippet, context
        forbidden_cols = {"text", "raw_text", "snippet", "context", "candidate_text", "content"}
        assert forbidden_cols.isdisjoint(set(row.keys())), f"Found forbidden column in schema: {set(row.keys())}"

        # Verify sensitive candidate text is NOT in any column value
        row_str = str(row)
        assert "SuperSecretName" not in row_str, "CRITICAL: Raw candidate PII leaked into SQLite feedback record!"

        # Verify structural fields are present
        assert row["candidate_type"] == "PERSON"
        assert row["action"] == FeedbackAction.REJECT.value
        assert row["source"] == "ner_detector"
        assert row["confidence"] == 0.95

    delete_document_record(doc_id)


def test_category_change_feedback_minimization():
    """Verify category correction records metadata without sensitive values."""
    doc_id = "doc_cat_change_test"
    save_document_metadata(doc_id, "memo.txt", "txt", "INGESTED", 1, 100)

    cand = Candidate(
        candidate_id="c_cat_1",
        document_id=doc_id,
        start=0,
        end=10,
        text="SecretEmail@test.com",
        type="PERSON",  # Incorrectly classified
        confidence=0.80,
        sources=["gliner"],
    )

    fb_id = FeedbackService.record_review_feedback(
        document_id=doc_id,
        candidate=cand,
        action="APPROVED",
        new_type="EMAIL",
    )

    records = get_feedback_records(doc_id=doc_id)
    assert len(records) == 1
    rec = records[0]
    assert rec["action"] == FeedbackAction.CATEGORY_CHANGE.value
    details = json.loads(rec["details"])
    assert details["new_type"] == "EMAIL"
    assert "SecretEmail" not in json.dumps(rec)

    delete_document_record(doc_id)


def test_manual_addition_feedback():
    """Verify manual redaction additions are logged as data-minimized events."""
    doc_id = "doc_manual_test"
    save_document_metadata(doc_id, "doc.txt", "txt", "INGESTED", 1, 100)

    cand = Candidate(
        candidate_id="c_man_1",
        document_id=doc_id,
        start=50,
        end=62,
        text="InternalCode",
        type="ID_LIKE",
        confidence=1.0,
        sources=["manual"],
    )

    fb_id = FeedbackService.record_manual_add_feedback(doc_id, cand)
    records = get_feedback_records(doc_id=doc_id)
    assert len(records) == 1
    assert records[0]["action"] == FeedbackAction.MANUAL_ADD.value
    assert records[0]["source"] == "manual"
    assert "InternalCode" not in str(records[0])

    delete_document_record(doc_id)


def test_opt_in_encrypted_alias_consent_requirement():
    """Verify that storing aliases fails closed without explicit opt-in consent."""
    req_no_consent = OptInAliasRequest(
        document_id="doc_alias_test",
        entity_id="ent_1",
        alias_value="Dr. Thorne",
        opt_in_consent=False,  # No consent
    )

    with pytest.raises(ValueError, match="Explicit opt-in consent is required"):
        FeedbackService.store_opt_in_alias(req_no_consent)


def test_opt_in_encrypted_alias_encryption_and_retrieval():
    """Verify authenticated AES-256-GCM encryption and round-trip retrieval."""
    doc_id = "doc_alias_enc_test"
    save_document_metadata(doc_id, "test.txt", "txt", "INGESTED", 1, 50)

    req = OptInAliasRequest(
        document_id=doc_id,
        entity_id="ent_thorne",
        alias_value="Aris Thorne",
        opt_in_consent=True,
        retention_days=15,
    )

    rec_id = FeedbackService.store_opt_in_alias(req)
    assert rec_id.startswith("enc_alias_")

    # Verify SQLite row contains ciphertext, NOT plaintext
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM opt_in_encrypted_aliases WHERE id = ?", (rec_id,))
        row = dict(cursor.fetchone())
        assert row["opt_in_consent"] == 1
        raw_cipher = row["encrypted_alias"]
        assert b"Aris Thorne" not in raw_cipher, "CRITICAL: Plaintext found in encrypted_alias column!"

    # Retrieve and decrypt
    aliases = FeedbackService.get_opt_in_aliases(doc_id)
    assert len(aliases) == 1
    assert aliases[0]["alias_value"] == "Aris Thorne"
    assert aliases[0]["entity_id"] == "ent_thorne"

    # Cleanup
    FeedbackService.clear_document_data(doc_id)
    assert len(FeedbackService.get_opt_in_aliases(doc_id)) == 0
    delete_document_record(doc_id)


def test_cascade_deletion():
    """Verify that deleting a document record removes feedback and aliases."""
    doc_id = "doc_cascade_test"
    save_document_metadata(doc_id, "audit.txt", "txt", "INGESTED", 1, 100)

    cand = Candidate(
        candidate_id="c_casc_1",
        document_id=doc_id,
        start=0,
        end=5,
        text="Dummy",
        type="PERSON",
        confidence=0.9,
    )
    FeedbackService.record_review_feedback(doc_id, cand, "APPROVED")
    FeedbackService.store_opt_in_alias(OptInAliasRequest(
        document_id=doc_id,
        entity_id="ent_casc",
        alias_value="AliasName",
        opt_in_consent=True,
    ))

    assert len(get_feedback_records(doc_id=doc_id)) == 1
    assert len(FeedbackService.get_opt_in_aliases(doc_id)) == 1

    # Cascade delete
    deleted = delete_document_record(doc_id)
    assert deleted is True

    # Assert all child records deleted
    assert len(get_feedback_records(doc_id=doc_id)) == 0
    assert len(FeedbackService.get_opt_in_aliases(doc_id)) == 0


def test_controlled_proposal_workflow_no_auto_mutation():
    """Verify feedback triggers structured proposals without modifying runtime patterns."""
    doc_id = "doc_proposal_test"
    save_document_metadata(doc_id, "log.txt", "txt", "INGESTED", 1, 100)

    # Capture initial regex patterns
    initial_patterns = dict(RegexDetector.PATTERNS)

    # Simulate 3 false positive rejections for a detector source
    for i in range(3):
        cand = Candidate(
            candidate_id=f"c_fp_{i}",
            document_id=doc_id,
            start=i * 10,
            end=(i + 1) * 10,
            text=f"FalseMatch{i}",
            type="ID_LIKE",
            confidence=0.70,
            sources=["test_regex_rule"],
        )
        FeedbackService.record_review_feedback(doc_id, cand, "REJECTED")

    # Analyze feedback
    report = FeedbackService.analyze_feedback(document_id=doc_id)
    assert report.total_feedback_events == 3
    assert report.action_counts[FeedbackAction.REJECT.value] == 3
    assert report.human_approval_required is True

    # Verify structured proposal was generated
    assert len(report.proposals) >= 1
    prop = report.proposals[0]
    assert prop.status == "PROPOSED"  # Status is strictly PROPOSED
    assert prop.rejection_rate == 1.0

    # Invariant: Regex patterns MUST NOT have been modified
    assert RegexDetector.PATTERNS == initial_patterns, "CRITICAL: Detection regex mutated at runtime without approval!"

    delete_document_record(doc_id)


def test_feedback_api_endpoints():
    """Test feedback analysis and alias management via HTTP API."""
    client = TestClient(app)

    # 1. Feedback Analysis Endpoint
    res = client.get("/api/feedback/analysis")
    assert res.status_code == 200
    data = res.json()
    assert "total_feedback_events" in data
    assert "proposals" in data

    # 2. Opt-in Alias Endpoints
    doc_id = "doc_api_alias_test"
    save_document_metadata(doc_id, "api.txt", "txt", "INGESTED", 1, 100)

    # Fails without consent
    bad_res = client.post(
        f"/api/documents/{doc_id}/aliases",
        json={"document_id": doc_id, "entity_id": "e1", "alias_value": "Alias", "opt_in_consent": False},
    )
    assert bad_res.status_code == 400

    # Succeeds with explicit consent
    good_res = client.post(
        f"/api/documents/{doc_id}/aliases",
        json={"document_id": doc_id, "entity_id": "e1", "alias_value": "Alias", "opt_in_consent": True},
    )
    assert good_res.status_code == 200
    assert good_res.json()["status"] == "STORED"

    # Get aliases
    get_res = client.get(f"/api/documents/{doc_id}/aliases")
    assert get_res.status_code == 200
    assert len(get_res.json()) == 1
    assert get_res.json()[0]["alias_value"] == "Alias"

    # Delete aliases
    del_res = client.delete(f"/api/documents/{doc_id}/aliases")
    assert del_res.status_code == 200

    delete_document_record(doc_id)


def test_active_learning_quorum_prefix_and_confidence_calibration():
    """Validate the complete 6-step PS3 Active-Learning lifecycle:
    1. Unseen custom ID prefix ('BDG-77510') is initially missed by baseline detection.
    2. Reviewer manually adds 'BDG-99201' and 'BDG-44102' on training/review sessions.
    3. Feedback is stored with zero raw PII (only structural prefix 'BDG', never '99201'/'44102').
    4. Malicious/invalid prefixes ('ISO-27001' or single unconfirmed occurrence) are NOT learned.
    5. Subsequent detection run on a new document automatically detects 'BDG-77510' as PENDING.
    6. Historical rejections calibrate detector confidence downward on borderline sources.
    """
    client = TestClient(app)

    # Step 1: Upload target document before active learning -> 'BDG-77510' is missed
    target_txt = "Security Roster: Officer Priya Nair assigned badge BDG-77510 at Gate 4."
    up_before = client.post(
        "/api/documents/upload",
        files={"file": ("roster_before.txt", target_txt.encode("utf-8"), "text/plain")},
    )
    assert up_before.status_code == 201
    doc_before_id = up_before.json()["document_id"]

    det_before = client.post(f"/api/documents/{doc_before_id}/detect").json()
    before_texts = {c["text"] for c in det_before["candidates"]}
    assert "BDG-77510" not in before_texts

    # Step 2: Reviewer manually adds 'BDG-99201' on doc 1 (quorum = 1/2 -> not yet active)
    train_txt = "Shift Log: Badge BDG-99201 and BDG-44102 under ISO-27001 compliance."
    up_train = client.post(
        "/api/documents/upload",
        files={"file": ("shift_log.txt", train_txt.encode("utf-8"), "text/plain")},
    )
    doc_train_id = up_train.json()["document_id"]
    client.post(f"/api/documents/{doc_train_id}/detect")

    idx1 = train_txt.index("BDG-99201")
    client.post(
        f"/api/documents/{doc_train_id}/candidates/manual",
        json={"start": idx1, "end": idx1 + len("BDG-99201"), "type": "ID_LIKE"},
    )
    # Single observation must not activate prefix learning yet (quorum=2)
    assert "BDG" not in FeedbackService.get_active_learning_profile()["learned_id_prefixes"]

    # Attempt to manually add blocked standard prefix 'ISO-27001' twice -> must NEVER be learned
    idx_iso = train_txt.index("ISO-27001")
    for _ in range(2):
        FeedbackService.record_manual_add_feedback(
            doc_train_id,
            Candidate(
                candidate_id="c_iso",
                document_id=doc_train_id,
                start=idx_iso,
                end=idx_iso + len("ISO-27001"),
                text="ISO-27001",
                type="ID_LIKE",
                confidence=1.0,
                sources=["manual"],
            ),
        )
    assert "ISO" not in FeedbackService.get_active_learning_profile()["learned_id_prefixes"]

    # Add second legitimate manual observation 'BDG-44102' -> reaches quorum (2/2)
    idx2 = train_txt.index("BDG-44102")
    client.post(
        f"/api/documents/{doc_train_id}/candidates/manual",
        json={"start": idx2, "end": idx2 + len("BDG-44102"), "type": "ID_LIKE"},
    )
    profile = FeedbackService.get_active_learning_profile()
    assert "BDG" in profile["learned_id_prefixes"]

    # Step 3: Verify SQLite feedback_records contains ZERO raw PII strings ('99201' and '44102' absent)
    all_fb_str = json.dumps(get_feedback_records())
    assert "99201" not in all_fb_str
    assert "44102" not in all_fb_str

    # Also record 3 rejections for ('ner', 'PERSON') to test empirical confidence calibration
    for i in range(3):
        FeedbackService.record_review_feedback(
            doc_train_id,
            Candidate(
                candidate_id=f"c_rej_{i}",
                document_id=doc_train_id,
                start=0,
                end=5,
                text="Noise",
                type="PERSON",
                confidence=0.80,
                sources=["ner"],
            ),
            action="REJECTED",
        )

    # Step 4 & 5: Subsequent detection run on unseen badge 'BDG-77510' now detects it!
    det_after = client.post(f"/api/documents/{doc_before_id}/detect").json()
    assert "active_learning" in det_after["detectors_run"]
    after_cands = det_after["candidates"]
    bdg_cand = next((c for c in after_cands if c["text"] == "BDG-77510"), None)
    assert bdg_cand is not None
    assert "active_learning" in bdg_cand["sources"]
    assert bdg_cand["review_status"] == "PENDING"  # Never auto-approved

    # Verify confidence calibration was applied to NER PERSON candidate
    person_cand = next((c for c in after_cands if c["type"] == "PERSON"), None)
    assert person_cand is not None
    assert "active_learning:high_rejection_caution" in person_cand["context_signals"]

    # Cleanup test sessions
    client.delete(f"/api/documents/{doc_before_id}")
    client.delete(f"/api/documents/{doc_train_id}")
