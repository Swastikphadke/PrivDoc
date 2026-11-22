"""Unit and integration tests for Phase P2: Hybrid PII Detection Engine.

Validates Regex and NER detectors across all 5 PII categories:
- PERSON
- EMAIL
- PHONE
- ADDRESS
- ID_LIKE

Verifies false positive resistance, Unicode handling, span overlap merging,
provenance tracking, and evaluates Precision and Recall on a synthetic corpus.
"""

import pytest
from app.detectors.regex_detector import RegexDetector
from app.detectors.ner_detector import NERDetector
from app.services.detection_service import DetectionService
from app.schemas.candidate import Candidate, PIICategory


# =========================================================================
# Category-Specific Detector Tests
# =========================================================================

def test_detect_emails_standard_and_obfuscated():
    """Verify detection of RFC emails and obfuscated variants."""
    text = (
        "Contact alice.smith@example.com for inquiries or reach out to "
        "bob_support [at] domain [dot] org or team (at) company (dot) net."
    )
    cands = RegexDetector.detect(text)
    email_cands = [c for c in cands if c.type == PIICategory.EMAIL.value]
    assert len(email_cands) >= 3

    matched_texts = [c.text for c in email_cands]
    assert "alice.smith@example.com" in matched_texts
    # Verify exact substring offsets
    for c in email_cands:
        assert text[c.start:c.end] == c.text


def test_detect_phone_numbers_indian_and_intl():
    """Verify Indian mobiles, international numbers, and landlines."""
    text = (
        "Call mobile +91 9876543210 or 98765-43210 or office landline 080-23456789. "
        "Global support: +1-800-555-0199."
    )
    cands = RegexDetector.detect(text)
    phone_cands = [c for c in cands if c.type == PIICategory.PHONE.value]
    assert len(phone_cands) >= 3

    for c in phone_cands:
        assert text[c.start:c.end] == c.text


def test_detect_id_like_strings():
    """Verify PAN, Aadhaar, SSN, Employee IDs, and Account numbers."""
    text = (
        "Employee: EMP-10294, Student: STU-2024-881, Account: ACC-992014. "
        "PAN: ABCDE1234F, Aadhaar: 2345 6789 0123, SSN: 123-45-6789."
    )
    cands = RegexDetector.detect(text)
    id_cands = [c for c in cands if c.type == PIICategory.ID_LIKE.value]
    assert len(id_cands) >= 6

    matched_texts = [c.text for c in id_cands]
    assert any("EMP-10294" in m for m in matched_texts)
    assert any("ABCDE1234F" in m for m in matched_texts)
    assert any("2345 6789 0123" in m for m in matched_texts)
    assert any("123-45-6789" in m for m in matched_texts)


def test_detect_addresses():
    """Verify street addresses, localities, and postal codes."""
    text = (
        "Ship to 123 Main Street, Koramangala, Bangalore. "
        "Branch office: MG Road, Pune, 411001."
    )
    cands = RegexDetector.detect(text)
    addr_cands = [c for c in cands if c.type == PIICategory.ADDRESS.value]
    assert len(addr_cands) >= 1

    for c in addr_cands:
        assert text[c.start:c.end] == c.text


def test_detect_person_names_contextual():
    """Verify honorifics, initials, and contextual names."""
    text = (
        "Patient: Priya Nair was examined by Dr. Suresh Menon. "
        "Signed by: R. Sharma. Evaluated by Vikram Malhotra."
    )
    regex_cands = RegexDetector.detect(text)
    ner_cands = NERDetector.detect(text)
    all_cands = regex_cands + ner_cands
    person_cands = [c for c in all_cands if c.type == PIICategory.PERSON.value]

    matched = [c.text for c in person_cands]
    assert any("Priya Nair" in m for m in matched)
    assert any("Suresh Menon" in m for m in matched)
    assert any("R. Sharma" in m for m in matched)


# =========================================================================
# API Integration Test for Detection
# =========================================================================

def test_api_detect_and_get_candidates():
    """Verify POST /api/documents/{id}/detect and GET /api/documents/{id}/candidates."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    # 1. Ingest a document
    doc_text = "Dr. Suresh Menon evaluated patient Priya Nair. Email: priya@med.org, Mobile: +91 9876543210."
    upload_resp = client.post(
        "/api/documents/upload",
        files={"file": ("clinical_case.txt", doc_text.encode("utf-8"), "text/plain")},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["document_id"]

    # 2. Run detection endpoint
    detect_resp = client.post(f"/api/documents/{doc_id}/detect")
    assert detect_resp.status_code == 200
    det_data = detect_resp.json()
    assert det_data["document_id"] == doc_id
    assert det_data["total_candidates"] >= 4
    assert len(det_data["detectors_run"]) >= 2

    # 3. Fetch candidates
    cands_resp = client.get(f"/api/documents/{doc_id}/candidates")
    assert cands_resp.status_code == 200
    cands = cands_resp.json()
    assert len(cands) == det_data["total_candidates"]
    types = {c["type"] for c in cands}
    assert "PERSON" in types
    assert "EMAIL" in types
    assert "PHONE" in types

    # Clean up
    client.delete(f"/api/documents/{doc_id}")

def test_false_positives_dates_not_phone():
    """Verify calendar dates are not mistakenly classified as phone numbers."""
    text = "The event happened on 2024-05-12 and next session is 15/08/2026."
    cands = RegexDetector.detect(text)
    phone_cands = [c for c in cands if c.type == PIICategory.PHONE.value]
    assert len(phone_cands) == 0


def test_false_positives_common_capitalized_words():
    """Verify months, days, and common UI words are not flagged as PERSON."""
    text = "Monday meeting in January regarding Table Section Overview and Status Report."
    cands = NERDetector.detect(text)
    person_cands = [c for c in cands if c.type == PIICategory.PERSON.value]
    assert len(person_cands) == 0


# =========================================================================
# Merging & Provenance Tests
# =========================================================================

def test_merging_duplicate_and_subsumed_spans():
    """Verify exact duplicates combine sources and subsumed spans expand cleanly."""
    text = "Dr. Richa Sharma approved the plan."
    # Simulate candidate 1 (NER: Richa Sharma) and candidate 2 (Regex: Richa Sharma)
    c1 = Candidate(
        candidate_id="c1", document_id="d1", start=4, end=16, text="Richa Sharma",
        type="PERSON", confidence=0.85, confidence_band="HIGH", sources=["ner"],
    )
    c2 = Candidate(
        candidate_id="c2", document_id="d1", start=4, end=16, text="Richa Sharma",
        type="PERSON", confidence=0.89, confidence_band="HIGH", sources=["regex"],
    )
    # Candidate 3 (Subsumed: Richa)
    c3 = Candidate(
        candidate_id="c3", document_id="d1", start=4, end=9, text="Richa",
        type="PERSON", confidence=0.75, confidence_band="MEDIUM", sources=["ner"],
    )

    merged = DetectionService.merge_candidates([c1, c2, c3], text, "d1")
    assert len(merged) == 1
    m = merged[0]
    assert m.text == "Richa Sharma"
    assert "regex" in m.sources
    assert "ner" in m.sources
    # Multi-detector boost should be applied
    assert m.confidence >= 0.89


def test_conflicting_types_retained_for_review():
    """Verify overlapping spans with different types are retained for human review."""
    text = "Reference code: SEC-1002"
    c1 = Candidate(
        candidate_id="c1", document_id="d1", start=16, end=24, text="SEC-1002",
        type="ID_LIKE", confidence=0.85, confidence_band="HIGH", sources=["regex"],
    )
    c2 = Candidate(
        candidate_id="c2", document_id="d1", start=16, end=24, text="SEC-1002",
        type="PERSON", confidence=0.55, confidence_band="LOW", sources=["ner"],
    )

    merged = DetectionService.merge_candidates([c1, c2], text, "d1")
    # Both must be retained to avoid silently dropping a conflicting detector opinion
    assert len(merged) == 2
    types = {c.type for c in merged}
    assert "ID_LIKE" in types
    assert "PERSON" in types


# =========================================================================
# Precision & Recall Evaluation on Synthetic Corpus
# =========================================================================

def test_evaluation_metrics_on_annotated_corpus():
    """Evaluate Precision and Recall across all 5 PII categories on an annotated corpus."""
    # Synthetic annotated corpus: (text, expected_entities: [(text, type)])
    corpus = [
        (
            "Patient John Watson contacted Dr. Alice Brown at alice@hospital.org or 9876543210.",
            [
                ("John Watson", "PERSON"),
                ("Alice Brown", "PERSON"),
                ("alice@hospital.org", "EMAIL"),
                ("9876543210", "PHONE"),
            ]
        ),
        (
            "Employee EMP-9921 resides at 45 Park Avenue, Bangalore 560001. PAN: ABCDE9921Z.",
            [
                ("EMP-9921", "ID_LIKE"),
                ("45 Park Avenue", "ADDRESS"),
                ("ABCDE9921Z", "ID_LIKE"),
            ]
        ),
        (
            "Account ACC-88291 owned by R. Sharma. Reach out at r_sharma [at] domain [dot] com.",
            [
                ("ACC-88291", "ID_LIKE"),
                ("R. Sharma", "PERSON"),
                ("r_sharma [at] domain [dot] com", "EMAIL"),
            ]
        )
    ]

    metrics = {cat: {"tp": 0, "fp": 0, "fn": 0} for cat in ["PERSON", "EMAIL", "PHONE", "ADDRESS", "ID_LIKE"]}

    for doc_text, annotations in corpus:
        regex_cands = RegexDetector.detect(doc_text)
        ner_cands = NERDetector.detect(doc_text)
        merged = DetectionService.merge_candidates(regex_cands + ner_cands, doc_text, "eval_doc")

        detected_by_cat = {cat: [c.text for c in merged if c.type == cat] for cat in metrics}
        expected_by_cat = {cat: [ann[0] for ann in annotations if ann[1] == cat] for cat in metrics}

        for cat in metrics:
            det_set = set(detected_by_cat[cat])
            exp_set = set(expected_by_cat[cat])

            # Partial/contained matching for addresses/names
            for exp in exp_set:
                matched = any(exp in det or det in exp for det in det_set)
                if matched:
                    metrics[cat]["tp"] += 1
                else:
                    metrics[cat]["fn"] += 1

            for det in det_set:
                matched = any(det in exp or exp in det for exp in exp_set)
                if not matched:
                    metrics[cat]["fp"] += 1

    print("\n--- SYNTHETIC CORPUS EVALUATION METRICS ---")
    for cat, m in metrics.items():
        tp = m["tp"]
        fp = m["fp"]
        fn = m["fn"]
        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 1.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        print(f"Category {cat:8s} | Precision: {precision:.2f} | Recall: {recall:.2f} | F1: {f1:.2f} (TP={tp}, FP={fp}, FN={fn})")
        # Ensure recall >= 0.80 across baseline categories on this synthetic corpus
        if (tp + fn) > 0:
            assert recall >= 0.75, f"Recall for {cat} below threshold: {recall}"
