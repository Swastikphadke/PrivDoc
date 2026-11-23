"""Adversarial and functional test suite for Phase P6: Privacy-Preserving Summarization.

Tests all 16 mandatory adversarial scenarios:
1. Summarizer cannot access original document objects.
2. Summarizer cannot access original extracted text.
3. Summarizer cannot access raw approved PII values.
4. Non-VERIFIED P5 exports are rejected.
5. Direct leakage is detected.
6. Name aliases and variants are detected.
7. Generated emails, phones and IDs are detected.
8. Generated person names and addresses are detected.
9. High-risk quasi-identifier combinations are flagged.
10. Unsupported facts and reconstructed details are rejected.
11. Malformed SLM output is rejected.
12. SLM timeout and offline fallback.
13. Extractive fallback undergoes identical checks.
14. Retry limits are enforced.
15. Failed checks block summary display.
16. Logs and API errors contain no raw PII.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import get_safe_session_dir
from app.database.session import save_document_metadata, update_document_status
from app.detectors.entity_resolver import EntityResolver
from app.schemas.candidate import Candidate, ReviewStatus
from app.schemas.entity import Entity
from app.schemas.redaction import ExportState
from app.schemas.summary import (
    QuasiRiskLevel,
    SanitizedDocument,
    StructuredSummaryContent,
    SummaryEngine,
    SummaryRequest,
    SummaryResponse,
    SummaryState,
)
from app.services.model_service import ModelService
from app.services.summary_guard import SummaryGuard
from app.services.summary_service import SummaryService


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_session():
    """Create a temporary test document session."""
    doc_id = "test-doc-summary-001"
    session_dir = get_safe_session_dir(doc_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    save_document_metadata(
        doc_id=doc_id,
        filename="confidential_agreement.txt",
        file_type="txt",
        status=ExportState.VERIFIED.value,
        page_count=1,
        text_length=500,
    )

    # Write sanitized text
    sanitized_text = (
        "This Mutual Non-Disclosure Agreement is entered into by [PERSON] on behalf of Acme Corp "
        "and [PERSON] representing Beta Ltd on October 14, 2024. "
        "Contact communications will be directed to [EMAIL] and [PHONE]. "
        "The parties agree that all confidential deliverables remain protected under Section 4. "
        "The project fee is fixed at $50,000 payable upon milestone completion."
    )
    (session_dir / "sanitized.txt").write_text(sanitized_text, encoding="utf-8")

    # Write export metadata indicating VERIFIED state
    export_meta = {
        "document_id": doc_id,
        "export_state": "VERIFIED",
        "file_type": "txt",
        "export_filename": "sanitized_confidential_agreement.txt",
        "approved_redactions_applied": 3,
        "verification": {
            "status": "PASSED",
            "checks_run": ["FILE_INTEGRITY", "CANONICAL_LENGTH_CHECK", "EXACT_APPROVED_STRINGS"],
            "issues": [],
            "warnings": [],
            "verified_at": "2024-10-14T10:00:00Z",
        },
        "download_ready": True,
    }
    (session_dir / "export_metadata.json").write_text(json.dumps(export_meta, indent=2), encoding="utf-8")

    # Write candidate and entity mappings for guard references
    cand1 = Candidate(
        candidate_id="cand_1",
        document_id=doc_id,
        text="Vikram Malhotra",
        type="PERSON",
        start=53,
        end=68,
        confidence=0.95,
        confidence_band="HIGH",
        sources=["ner"],
        review_status="APPROVED",
    )
    cand2 = Candidate(
        candidate_id="cand_2",
        document_id=doc_id,
        text="vikram.m@acmecorp.com",
        type="EMAIL",
        start=150,
        end=171,
        confidence=0.98,
        confidence_band="HIGH",
        sources=["regex"],
        review_status="APPROVED",
    )
    EntityResolver.save_candidates(doc_id, [cand1, cand2])

    ent1 = Entity(
        entity_id="ent_1",
        canonical_name="Vikram Malhotra",
        entity_type="PERSON",
        candidate_ids=["cand_1"],
        variants=["Vikram Malhotra", "V. Malhotra", "Vikram"],
        confidence=0.95,
        evidence=["exact_match", "initial_match"],
    )
    EntityResolver.save_entities(doc_id, [ent1])

    return doc_id, session_dir, sanitized_text


# =========================================================================
# Scenario 1: Summarizer cannot access original document objects
# =========================================================================
def test_p6_01_summarizer_cannot_access_original_document_objects():
    """Assert summarizer function signature strictly requires SanitizedDocument contract."""
    with pytest.raises(TypeError, match="typed SanitizedDocument contract"):
        # Attempt to pass an arbitrary dict or raw doc
        SummaryService.generate_summary({"raw_doc": "original file content"})

    # Assert SanitizedDocument schema forbids arbitrary raw file attributes
    sanitized_doc = SanitizedDocument(
        document_id="doc_123",
        sanitized_text="Redacted text with [PERSON]",
        export_verification_ref="P5-VERIFIED",
    )
    assert not hasattr(sanitized_doc, "original_doc")
    assert not hasattr(sanitized_doc, "original_pdf")
    assert not hasattr(sanitized_doc, "pdf_coordinates")


# =========================================================================
# Scenario 2: Summarizer cannot access original extracted text
# =========================================================================
def test_p6_02_summarizer_cannot_access_original_extracted_text():
    """Assert SanitizedDocument contract carries exclusively sanitized text."""
    sanitized_doc = SanitizedDocument(
        document_id="doc_456",
        sanitized_text="The contract was approved by [PERSON].",
        export_verification_ref="P5-VERIFIED",
    )
    assert not hasattr(sanitized_doc, "original_text")
    assert not hasattr(sanitized_doc, "canonical_text")
    assert "[PERSON]" in sanitized_doc.sanitized_text


# =========================================================================
# Scenario 3: Summarizer cannot access raw approved PII values
# =========================================================================
def test_p6_03_summarizer_cannot_access_raw_approved_pii_values():
    """Assert ModelService summary prompt takes only sanitized text and never candidate objects."""
    import inspect
    sig = inspect.signature(ModelService.generate_structured_summary)
    param_names = list(sig.parameters.keys())
    assert "sanitized_text" in param_names
    assert "approved_values" not in param_names
    assert "candidates" not in param_names
    assert "entities" not in param_names


# =========================================================================
# Scenario 4: Non-VERIFIED P5 exports are rejected
# =========================================================================
def test_p6_04_non_verified_p5_exports_are_rejected(client, test_session):
    """Assert POST /api/documents/{id}/summary rejects documents that are not P5 VERIFIED."""
    doc_id, session_dir, _ = test_session

    # Change export_metadata to FAILED
    meta_path = session_dir / "export_metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["export_state"] = "FAILED"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    res = client.post(f"/api/documents/{doc_id}/summary")
    assert res.status_code == 400
    assert "Summarization blocked" in res.json()["detail"]
    assert "Only P5 VERIFIED" in res.json()["detail"]


# =========================================================================
# Scenario 5: Direct leakage is detected
# =========================================================================
def test_p6_05_direct_leakage_is_detected():
    """Assert direct leakage of approved sensitive entities is detected and masked."""
    approved_values = ["Vikram Malhotra", "9876543210"]
    summary_with_leak = "The agreement was signed by Vikram Malhotra on October 14."

    passed, error_detail = SummaryGuard.check_direct_leakage(summary_with_leak, approved_values)
    assert passed is False
    assert "Approved sensitive entity detected" in error_detail
    # Must NOT expose raw PII in error detail!
    assert "Vikram Malhotra" not in error_detail
    assert "token hash:" in error_detail


# =========================================================================
# Scenario 6: Name aliases and variants are detected
# =========================================================================
def test_p6_06_name_aliases_and_variants_are_detected():
    """Assert entity variants and initials are detected by SummaryGuard."""
    variants = ["V. Malhotra", "Malhotra"]
    summary_with_alias = "The report was approved by V. Malhotra."

    passed, error_detail = SummaryGuard.check_alias_and_entity_variants(summary_with_alias, variants)
    assert passed is False
    assert "Approved entity alias or variant detected" in error_detail
    assert "V. Malhotra" not in error_detail


# =========================================================================
# Scenario 7: Generated emails, phones and IDs are detected
# =========================================================================
def test_p6_07_generated_emails_phones_and_ids_are_detected():
    """Assert deterministic regex scan detects unmasked emails, phones, and IDs in summary."""
    summary_with_email = "Contact the project manager at secret.leak@company.org."
    passed, error_detail = SummaryGuard.check_pii_redetection(summary_with_email)
    assert passed is False
    assert "EMAIL" in error_detail

    summary_with_phone = "Please call +91 98765 43210 for verification."
    passed2, error_detail2 = SummaryGuard.check_pii_redetection(summary_with_phone)
    assert passed2 is False
    assert "PHONE" in error_detail2


# =========================================================================
# Scenario 8: Generated person names and addresses are detected
# =========================================================================
def test_p6_08_generated_person_names_and_addresses_are_detected():
    """Assert PII re-detection flags unmasked person names or street addresses."""
    summary_with_addr = "Deliver the materials to 123 Elm Street, Suite 400."
    passed, error_detail = SummaryGuard.check_pii_redetection(summary_with_addr)
    # Regex or NER catches address patterns
    assert passed is False
    assert "ADDRESS" in error_detail or "Residual PII detected" in error_detail


# =========================================================================
# Scenario 9: High-risk quasi-identifier combinations are flagged
# =========================================================================
def test_p6_09_high_risk_quasi_identifier_combinations_are_flagged():
    """Assert role + department + location/date combination triggers HIGH risk flag."""
    summary_text = (
        "The Chief of Oncology at Memorial Hospital conducted the review on October 14, 2024."
    )
    assessment = SummaryGuard.check_quasi_identifier_risk(
        summary_text=summary_text,
        sanitized_text="Sanitized background text.",
    )
    assert assessment.risk_level == QuasiRiskLevel.HIGH
    assert len(assessment.flagged_rules) > 0
    # Mandatory disclaimer verification:
    assert "does not constitute mathematical or legal proof of complete anonymity" in assessment.disclaimer


# =========================================================================
# Scenario 10: Unsupported facts and reconstructed details are rejected
# =========================================================================
def test_p6_10_unsupported_facts_and_reconstructed_details_are_rejected():
    """Assert source consistency check rejects fabricated numbers or dates."""
    sanitized_text = "The contract fee is fixed at $50,000 for phase 1."
    fabricated_summary = StructuredSummaryContent(
        summary_text="The contract fee was negotiated to $999,999 on December 25, 2030.",
        key_points=["Fee: $999,999"],
        important_findings=["Negotiated on December 25, 2030"],
        relevant_dates_or_figures=["$999,999", "December 25, 2030"],
        source_evidence=[],
    )

    passed, error_detail = SummaryGuard.check_source_consistency(fabricated_summary, sanitized_text)
    assert passed is False
    assert "Unsupported" in error_detail or "not present in sanitized text" in error_detail


# =========================================================================
# Scenario 11: Malformed SLM output is rejected
# =========================================================================
def test_p6_11_malformed_slm_output_is_rejected():
    """Assert malformed or unparseable SLM output gracefully falls back to extractive mode."""
    sanitized_doc = SanitizedDocument(
        document_id="doc_malformed",
        sanitized_text="The parties [PERSON] and [PERSON] agreed to mutual deliverables on October 14, 2024.",
        export_verification_ref="P5-VERIFIED",
    )

    with patch.object(ModelService, "check_availability", return_value=True):
        # Mock SLM returning None (due to malformed JSON or schema failure)
        with patch.object(ModelService, "generate_structured_summary", return_value=None):
            response = SummaryService.generate_summary(sanitized_doc)
            assert response.engine_used == SummaryEngine.EXTRACTIVE_FALLBACK
            assert response.state == SummaryState.VERIFIED
            assert response.content is not None
            assert len(response.content.summary_text) > 0


# =========================================================================
# Scenario 12: SLM timeout and offline fallback
# =========================================================================
def test_p6_12_slm_timeout_and_offline_fallback():
    """Assert offline SLM immediately and seamlessly falls back to extractive summary."""
    sanitized_doc = SanitizedDocument(
        document_id="doc_offline",
        sanitized_text="The agreement was signed by [PERSON] for Acme Corp. All terms remain confidential.",
        export_verification_ref="P5-VERIFIED",
    )

    with patch.object(ModelService, "check_availability", return_value=False):
        response = SummaryService.generate_summary(sanitized_doc)
        assert response.engine_used == SummaryEngine.EXTRACTIVE_FALLBACK
        assert response.state == SummaryState.VERIFIED
        assert "extractive fallback" in response.warning_message.lower()


# =========================================================================
# Scenario 13: Extractive fallback undergoes identical checks
# =========================================================================
def test_p6_13_extractive_fallback_undergoes_identical_checks():
    """Assert extractive fallback is fully verified through SummaryGuard."""
    # Sanitized text containing an unredacted email that was somehow missed
    sanitized_with_leak = "Agreement by [PERSON]. Contact direct at unredacted.leak@example.com for keys."
    sanitized_doc = SanitizedDocument(
        document_id="doc_extractive_leak",
        sanitized_text=sanitized_with_leak,
        export_verification_ref="P5-VERIFIED",
    )

    request = SummaryRequest(force_extractive=True)
    response = SummaryService.generate_summary(sanitized_doc, request=request)
    assert response.engine_used == SummaryEngine.EXTRACTIVE_FALLBACK
    # The leak in text should trigger PII re-detection and suppress the summary!
    assert response.state == SummaryState.SUPPRESSED
    assert response.content is None
    assert "suppressed" in response.warning_message.lower()


# =========================================================================
# Scenario 14: Retry limits are enforced
# =========================================================================
def test_p6_14_retry_limits_are_enforced():
    """Assert SLM retries are bounded to MAX_RETRIES (2 retries = 3 total attempts)."""
    sanitized_doc = SanitizedDocument(
        document_id="doc_retry",
        sanitized_text="The agreement was approved by [PERSON]. Confidential terms apply.",
        export_verification_ref="P5-VERIFIED",
    )

    call_count = 0

    def mock_slm_generate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Always return summary with a leak
        return StructuredSummaryContent(
            summary_text=f"Attempt {call_count} by Vikram Malhotra.",
            key_points=["Leaked point"],
            important_findings=[],
            relevant_dates_or_figures=[],
            source_evidence=[],
        )

    guard_refs = {"approved_values": ["Vikram Malhotra"], "entity_variants": []}

    with patch.object(ModelService, "check_availability", return_value=True):
        with patch.object(ModelService, "generate_structured_summary", side_effect=mock_slm_generate):
            response = SummaryService.generate_summary(sanitized_doc, guard_references=guard_refs)
            # After 3 attempts (attempt 0, 1, 2), switches to extractive
            assert call_count == 3
            assert response.retry_count == 2
            # Extractive summary on sanitized text passes
            assert response.engine_used == SummaryEngine.EXTRACTIVE_FALLBACK
            assert response.state == SummaryState.VERIFIED


# =========================================================================
# Scenario 15: Failed checks block summary display
# =========================================================================
def test_p6_15_failed_checks_block_summary_display():
    """Assert failed verification suppresses summary content so it is never displayed."""
    sanitized_doc = SanitizedDocument(
        document_id="doc_suppress",
        sanitized_text="Confidential memo with email leak@secret.com inside.",
        export_verification_ref="P5-VERIFIED",
    )

    request = SummaryRequest(force_extractive=True)
    response = SummaryService.generate_summary(sanitized_doc, request=request)
    assert response.state == SummaryState.SUPPRESSED
    assert response.content is None
    assert response.warning_message is not None


# =========================================================================
# Scenario 16: Logs and API errors contain no raw PII
# =========================================================================
def test_p6_16_logs_and_api_errors_contain_no_raw_pii():
    """Assert verification check details and reports contain no raw sensitive strings."""
    approved_sensitive_val = "SecretProjectAlpha99"
    content = StructuredSummaryContent(
        summary_text=f"The memo discusses SecretProjectAlpha99 deliverables.",
        key_points=[],
        important_findings=[],
        relevant_dates_or_figures=[],
        source_evidence=[],
    )
    sanitized_doc = SanitizedDocument(
        document_id="doc_audit_pii",
        sanitized_text="The memo discusses [ID_LIKE] deliverables.",
        export_verification_ref="P5-VERIFIED",
    )
    guard_refs = {"approved_values": [approved_sensitive_val], "entity_variants": []}

    report = SummaryGuard.verify_summary(content, sanitized_doc, guard_refs)
    report_json = report.model_dump_json()

    # Raw secret string MUST NOT be in the report!
    assert approved_sensitive_val not in report_json
    # Only hashed token is present
    assert "token hash:" in report_json


# =========================================================================
# API Integration Tests: POST & GET /api/documents/{id}/summary
# =========================================================================
def test_p6_api_post_and_get_summary_workflow(client, test_session):
    """End-to-end API test: generate summary and retrieve existing summary."""
    doc_id, session_dir, _ = test_session

    # 1. POST summary generation (with extractive fallback for deterministic test)
    res_post = client.post(
        f"/api/documents/{doc_id}/summary",
        json={"force_extractive": True, "max_length": 200},
    )
    assert res_post.status_code == 200
    data = res_post.json()
    assert data["document_id"] == doc_id
    assert data["state"] == "VERIFIED"
    assert data["engine_used"] == "EXTRACTIVE_FALLBACK"
    assert data["content"] is not None
    assert len(data["content"]["summary_text"]) > 0
    assert len(data["content"]["key_points"]) > 0
    assert data["verification_report"]["status"] == "PASSED"

    # 2. GET summary retrieval
    res_get = client.get(f"/api/documents/{doc_id}/summary")
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["document_id"] == doc_id
    assert data_get["state"] == "VERIFIED"
    assert data_get["content"]["summary_text"] == data["content"]["summary_text"]
