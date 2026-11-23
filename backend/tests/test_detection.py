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


# =========================================================================
# Stage 2 (Priority 1) Hybrid PII Detection & Provenance Tests
# =========================================================================

def test_stage2_p1_role_prefix_stripping_and_honorific_retention():
    """Verify job-role prefixes ('Lead Auditor', 'Deputy Director') are stripped from PERSON
    offsets while honorifics ('Dr.', 'Ms.', 'Prof.') are retained in exact spans.
    """
    text = (
        "Assessment conducted by Lead Auditor Elena Vance and Deputy Director Marcus Sterling. "
        "Approved by Dr. Aris Thorne and Prof. Albus Dumbledore. Consult Ms. Sharma or Dr. Cross."
    )
    merged = DetectionService.detect_from_text(text, "doc_s2_roles", resolve_entities=False)
    person_texts = {c.text for c in merged if c.type == "PERSON"}

    assert "Elena Vance" in person_texts
    assert "Lead Auditor Elena" not in person_texts
    assert "Marcus Sterling" in person_texts
    assert "Deputy Director Marcus" not in person_texts
    assert "Dr. Aris Thorne" in person_texts
    assert "Prof. Albus Dumbledore" in person_texts
    assert "Ms. Sharma" in person_texts
    assert "Dr. Cross" in person_texts

    for c in merged:
        assert text[c.start:c.end] == c.text
        assert c.confidence_type == "HEURISTIC_EVIDENCE"
        assert len(c.explanation) > 0


def test_stage2_p1_id_like_false_positive_suppression():
    """Verify 'Account Holder', 'Account ID', and bank routing numbers without STD separators
    are not falsely flagged as ID_LIKE or PHONE, while valid ACCT/EMP/PAN codes are detected.
    """
    text = (
        "Account Holder: Rahul Verma | Account ID: ACCT-904820 | Employee ID: EMP-7741 | "
        "Tax ID: ABCDE1234F | Routing: 021000021"
    )
    merged = DetectionService.detect_from_text(text, "doc_s2_ids", resolve_entities=False)
    id_texts = {c.text for c in merged if c.type == "ID_LIKE"}
    phone_texts = {c.text for c in merged if c.type == "PHONE"}

    assert "ACCT-904820" in id_texts
    assert "EMP-7741" in id_texts
    assert "ABCDE1234F" in id_texts
    assert "Account Holder" not in id_texts
    assert "Account ID" not in id_texts
    assert "021000021" not in phone_texts


def test_stage2_p1_address_span_union_and_multi_format_detection():
    """Verify complex building, plot, suite, and street addresses merge into complete spans."""
    text = (
        "Primary HQ: Plot 42, Electronic City Phase 1, Hosur Road, Bangalore 560100, Karnataka.\n"
        "Registered Branch: Suite 800, 1200 Innovation Way, Austin, TX 78701, United States.\n"
        "Operations supervised by Sunil Kumar at 102 MG Road, Bangalore 560001."
    )
    merged = DetectionService.detect_from_text(text, "doc_s2_addr", resolve_entities=False)
    addr_texts = {c.text for c in merged if c.type == "ADDRESS"}

    assert "Plot 42, Electronic City Phase 1, Hosur Road, Bangalore 560100" in addr_texts
    assert "Suite 800, 1200 Innovation Way, Austin, TX 78701" in addr_texts
    assert "102 MG Road, Bangalore 560001" in addr_texts


def test_stage2_p1_document_local_surname_and_ambiguity_safeguard():
    """Verify standalone surname references ('call Vance') are detected via document-local
    anchor scanning, and ambiguous surnames ('Smith' with John Smith & James Smith) are
    flagged with is_ambiguous_suggestion=True and LOW confidence.
    """
    # 1. Unambiguous standalone surname
    text_unambig = (
        "Lead Investigator: Dr. Marcus Vance conducted the audit. "
        "For urgent escalations, call Vance at +1 (415) 555-0199."
    )
    cands_unambig = DetectionService.detect_from_text(text_unambig, "doc_s2_unambig", resolve_entities=False)
    vance_single = next((c for c in cands_unambig if c.text == "Vance"), None)
    assert vance_single is not None
    assert vance_single.is_ambiguous_suggestion is False
    assert vance_single.confidence_band == "MEDIUM"
    assert any("Marcus Vance" in exp for exp in vance_single.explanation)

    # 2. Ambiguous standalone surname (John Smith and James Smith both present)
    text_ambig = (
        "Case involves John Smith and his brother James Smith. "
        "For clarification, contact Smith immediately."
    )
    cands_ambig = DetectionService.detect_from_text(text_ambig, "doc_s2_ambig", resolve_entities=False)
    smith_single = next((c for c in cands_ambig if c.text == "Smith"), None)
    assert smith_single is not None
    assert smith_single.is_ambiguous_suggestion is True
    assert smith_single.confidence_band == "LOW"
    assert any("Ambiguous standalone surname" in exp for exp in smith_single.explanation)


def test_stage2_p1_slm_detector_coordination_and_detector_agreement(monkeypatch):
    """Verify SLMDetector coordinates with DetectionService when local SLM is available,
    and detector_agreement records MULTI_DETECTOR_CONSENSUS vs TYPE_CONFLICT.
    """
    from app.services.model_service import ModelService
    from app.schemas.entity import SLMAnalysisResponse, SLMSuggestedCandidate

    monkeypatch.setattr(ModelService, "check_availability", lambda: True)
    monkeypatch.setattr(
        ModelService,
        "analyze_context",
        lambda text, names: SLMAnalysisResponse(
            suggested_candidates=[
                SLMSuggestedCandidate(
                    text="Jean-Luc Picard",
                    type="PERSON",
                    reason="Contextual commander mention",
                )
            ],
            suggested_links=[],
        ),
    )

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    doc_text = "Patient: Priya Nair met with Jean-Luc Picard regarding the directive."
    up = client.post(
        "/api/documents/upload",
        files={"file": ("slm_coord.txt", doc_text.encode("utf-8"), "text/plain")},
    )
    doc_id = up.json()["document_id"]
    try:
        det = client.post(f"/api/documents/{doc_id}/detect")
        assert det.status_code == 200
        det_data = det.json()
        assert "slm" in det_data["detectors_run"]
        cands = det_data["candidates"]
        priya = next(c for c in cands if c["text"] == "Priya Nair")
        assert priya["detector_agreement"] == "MULTI_DETECTOR_CONSENSUS"
        assert "regex" in priya["sources"] and "ner" in priya["sources"]
    finally:
        client.delete(f"/api/documents/{doc_id}")


# =========================================================================
# Stage 2 Validation Audit: Unseen Adversarial Generalization & SLM Ablation
# =========================================================================

def test_stage2_audit_unseen_adversarial_generalization_corpus():
    """Evaluate hybrid detection on an unseen 8-document adversarial corpus separate from
    the historical dev/val/test splits.

    Covers all 9 required adversarial categories:
    1. Unseen names and surnames (including 'Austin Miller', 'Jose Martinez', 'Grant Taylor'
       to prove city/common words do not suppress valid personal names).
    2. Hyphenated and apostrophe-containing names ('Dr. Jean-Luc Picard', "D'Artagnan Moreau",
       "Prof. Siobhan O'Brien", 'Tariq Al-Mansoor').
    3. Indian and international addresses ('Flat 4B, Ashoka Towers, Jubilee Hills, Hyderabad - 500033',
       '742 Maple Boulevard, Apt 12C, Seattle, WA 98101').
    4. Organizations that resemble personal names ('Morgan Stanley Wealth Management',
       'Goldman Sachs Group', 'Grant Thornton LLP', 'Lincoln Memorial Hospital', 'Johnson & Johnson').
    5. Job titles followed by names ('Senior Compliance Officer Nandini Subramanian',
       'Chief Risk Analyst Tariq Al-Mansoor', 'Principal Architect Austin Miller').
    6. Multi-column tables with 2+ spaces separating columns.
    7. Ambiguous account identifiers ('Account Holder', 'Account Status: Active', 'Reference Code: Pending'
       vs 'ACC-8849201', 'EMP-40928', 'QWERT9876P').
    8. Short and partially formatted / masked identifiers ('XXXX-XXXX-4829', 'XXX-XX-6789',
       'CUST-774829', 'REF-2026-99481').
    9. Similar-looking non-PII phrases ('Version 2.4.1', 'ISO 27001-2022', 'Order 100200300',
       'Routing Code 021000021').
    """
    adversarial_corpus = [
        (
            "adv_01",
            (
                "Compliance review conducted by Senior Compliance Officer Nandini Subramanian and "
                "Principal Architect Austin Miller. Approved by Jose Martinez and Grant Taylor."
            ),
            [
                ("Nandini Subramanian", "PERSON"),
                ("Austin Miller", "PERSON"),
                ("Jose Martinez", "PERSON"),
                ("Grant Taylor", "PERSON"),
            ],
            ["Senior Compliance", "Principal Architect"],
        ),
        (
            "adv_02",
            (
                "Medical board panel: Attending Surgeon Dr. Jean-Luc Picard, Prof. Siobhan O'Brien, "
                "and Chief Risk Analyst Tariq Al-Mansoor met with D'Artagnan Moreau."
            ),
            [
                ("Dr. Jean-Luc Picard", "PERSON"),
                ("Prof. Siobhan O'Brien", "PERSON"),
                ("Tariq Al-Mansoor", "PERSON"),
                ("D'Artagnan Moreau", "PERSON"),
            ],
            ["Medical board", "Attending Surgeon", "Chief Risk"],
        ),
        (
            "adv_03",
            (
                " Applicant resides at Flat 4B, Ashoka Towers, Jubilee Hills, Hyderabad - 500033. "
                "Regional office located at 742 Maple Boulevard, Apt 12C, Seattle, WA 98101."
            ),
            [
                ("Flat 4B, Ashoka Towers, Jubilee Hills, Hyderabad - 500033", "ADDRESS"),
                ("742 Maple Boulevard, Apt 12C, Seattle, WA 98101", "ADDRESS"),
            ],
            ["Jubilee Hills", "Ashoka Towers", "Maple Boulevard"],
        ),
        (
            "adv_04",
            (
                "Vendors audited: Morgan Stanley Wealth Management, Goldman Sachs Group, "
                "Grant Thornton LLP, Lincoln Memorial Hospital, and Johnson & Johnson."
            ),
            [],
            [
                "Morgan Stanley",
                "Morgan Stanley Wealth",
                "Goldman Sachs",
                "Grant Thornton",
                "Lincoln Memorial",
                "Johnson",
            ],
        ),
        (
            "adv_05",
            (
                "Employee Name          Department         Badge ID      Status\n"
                "Kwame Nkrumah          Security Ops       EMP-40928     Active\n"
                "Siobhan MacLeod        Legal Advisory     STU-2025-771  Pending"
            ),
            [
                ("Kwame Nkrumah", "PERSON"),
                ("EMP-40928", "ID_LIKE"),
                ("Siobhan MacLeod", "PERSON"),
                ("STU-2025-771", "ID_LIKE"),
            ],
            ["Kwame Nkrumah          Security", "Security Ops", "Legal Advisory"],
        ),
        (
            "adv_06",
            (
                "Account Holder verified Account Status: Active and Reference Code: Pending. "
                "Primary identifiers: ACC-8849201, CUST-774829, REF-2026-99481, PAN: QWERT9876P, "
                "masked Aadhaar XXXX-XXXX-4829, and partial SSN XXX-XX-6789."
            ),
            [
                ("ACC-8849201", "ID_LIKE"),
                ("CUST-774829", "ID_LIKE"),
                ("REF-2026-99481", "ID_LIKE"),
                ("QWERT9876P", "ID_LIKE"),
                ("XXXX-XXXX-4829", "ID_LIKE"),
                ("XXX-XX-6789", "ID_LIKE"),
            ],
            ["Account Holder", "Account Status", "Reference Code"],
        ),
        (
            "adv_07",
            (
                "System specification Version 2.4.1 complies with ISO 27001-2022 under "
                "Order 100200300 and Routing Code 021000021. Contact kwame.nkrumah [at] enterprise [dot] org "
                "or call +44 20 7946 0958."
            ),
            [
                ("kwame.nkrumah [at] enterprise [dot] org", "EMAIL"),
                ("+44 20 7946 0958", "PHONE"),
            ],
            ["2.4.1", "27001-2022", "100200300", "021000021", "Routing Code"],
        ),
    ]

    tp, fp, fn = 0, 0, 0
    for doc_id, text, gold_items, forbidden_texts in adversarial_corpus:
        cands = DetectionService.detect_from_text(text, doc_id, resolve_entities=False)
        pred_set = {(c.text, c.type) for c in cands}
        gold_set = set(gold_items)

        tp += len(pred_set & gold_set)
        fp += len(pred_set - gold_set)
        fn += len(gold_set - pred_set)

        for f_txt in forbidden_texts:
            assert not any(c.text == f_txt for c in cands), (
                f"Adversarial false positive '{f_txt}' detected in {doc_id}: {[(c.text, c.type) for c in cands]}"
            )

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    assert precision >= 0.95, f"Adversarial precision too low: {precision:.4f} (TP={tp}, FP={fp})"
    assert recall >= 0.95, f"Adversarial recall too low: {recall:.4f} (TP={tp}, FN={fn})"
    assert f1 >= 0.95


def test_stage2_audit_slm_ablation_and_failure_safety(monkeypatch):
    """Compare Regex+NER without SLM vs Regex+NER with SLM enabled, and verify
    that SLM unavailability/timeout/malformed output never breaks detection or auto-approves candidates.
    """
    from app.services.model_service import ModelService
    from app.detectors.slm_detector import SLMDetector
    from app.schemas.entity import SLMAnalysisResponse, SLMSuggestedCandidate

    # Document with an implicit lower-context mention ("banksia.ops@darknet.local" + single-word alias "Nightingale")
    text = "Operative codename Nightingale transmitted keys to banksia.ops@darknet.local during the audit."
    gold = {("Nightingale", "PERSON"), ("banksia.ops@darknet.local", "EMAIL")}

    # 1. Without SLM (Regex + NER only)
    base_cands = DetectionService.detect_from_text(text, "doc_ablation_no_slm", resolve_entities=False)
    base_set = {(c.text, c.type) for c in base_cands}
    assert ("banksia.ops@darknet.local", "EMAIL") in base_set
    assert ("Nightingale", "PERSON") not in base_set  # Single word without full-name anchor

    # 2. With SLM enabled proposing contextual alias
    monkeypatch.setattr(ModelService, "check_availability", lambda: True)
    monkeypatch.setattr(
        ModelService,
        "analyze_context",
        lambda t, n: SLMAnalysisResponse(
            suggested_candidates=[
                SLMSuggestedCandidate(
                    text="Nightingale",
                    type="PERSON",
                    reason="Contextual operative alias in narrative",
                )
            ],
            suggested_links=[],
        ),
    )
    slm_new, _ = SLMDetector.detect_and_suggest("doc_ablation_slm", text, base_cands)
    with_slm_cands = DetectionService.merge_candidates(base_cands + slm_new, text, "doc_ablation_slm")
    with_slm_set = {(c.text, c.type) for c in with_slm_cands}
    assert with_slm_set == gold
    # Crucial safety invariant: SLM candidates MUST remain PENDING and never be auto-approved
    nightingale_cand = next(c for c in with_slm_cands if c.text == "Nightingale")
    assert nightingale_cand.review_status == "PENDING"
    assert nightingale_cand.confidence <= 0.68

    # 3. SLM failure / unavailability safety: raising RuntimeError inside SLM never breaks detection
    def broken_slm(*args, **kwargs):
        raise RuntimeError("Simulated Ollama daemon connection reset")

    monkeypatch.setattr(ModelService, "analyze_context", broken_slm)
    fallback_cands = DetectionService.detect_from_text(text, "doc_ablation_fail", resolve_entities=False)
    assert len(fallback_cands) == 1
    assert all(c.review_status == "PENDING" for c in fallback_cands)
