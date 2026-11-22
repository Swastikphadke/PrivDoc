"""Unit and Integration Tests for Phase P3: Entity Resolution & Local SLM Integration.

Tests cover:
1. Full name and matching initial ("Richa Sharma" & "R. Sharma").
2. Full name and title-based variant ("Richa Sharma" & "Ms. Sharma").
3. Similar but different names (e.g. "Anil Sharma" vs "Sunil Sharma" - do NOT merge).
4. Two employees sharing the same surname (e.g. "Anil Kumar" vs "Sunil Kumar" - do NOT merge).
5. Ambiguous initials ("J. Smith" with "John Smith" and "James Smith" - no auto-merge).
6. Repeated references across text (exact matches grouped into single entity).
7. Malformed / non-schema SLM JSON handling (safely discarded, no crash).
8. SLM timeout handling (graceful degraded mode).
9. SLM unavailable / connection error handling (graceful degraded mode).
10. Manual link, unlink, and merge operations.
11. Full API endpoint lifecycle (/entities/resolve, /entities, /entities/link).
"""

import json
from unittest.mock import MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from app.detectors.entity_resolver import EntityResolver
from app.main import app
from app.schemas.candidate import Candidate
from app.schemas.entity import (
    EntityLinkAction,
    EntityLinkRequest,
    SLMAnalysisResponse,
    SLMSuggestedCandidate,
    SLMSuggestedLink,
)
from app.services.model_service import ModelService

client = TestClient(app)


def _make_candidate(cand_id: str, text: str, cand_type: str = "PERSON", start: int = 0) -> Candidate:
    """Helper to instantiate mock candidates for unit testing."""
    return Candidate(
        candidate_id=cand_id,
        document_id="doc_test_session",
        start=start,
        end=start + len(text),
        text=text,
        type=cand_type,
        confidence=0.90,
        confidence_band="HIGH",
        sources=["ner"],
        review_status="PENDING",
    )


# =========================================================================
# 1. Exact Match and Repeated Occurrences
# =========================================================================

def test_exact_matches_grouped_together(tmp_path, monkeypatch):
    """Multiple occurrences of the same name should cluster into one entity with confidence 1.0."""
    monkeypatch.setattr("app.detectors.entity_resolver.get_safe_session_dir", lambda _: tmp_path)

    cands = [
        _make_candidate("c1", "Richa Sharma", start=10),
        _make_candidate("c2", "Richa Sharma", start=80),
        _make_candidate("c3", "richa sharma", start=150),
    ]

    resp = EntityResolver.resolve_entities("doc_test", cands, use_slm=False)
    assert resp.total_entities == 1
    entity = resp.entities[0]
    assert entity.canonical_name == "Richa Sharma"
    assert len(entity.candidate_ids) == 3
    assert entity.confidence == 1.0
    assert "Exact normalized string match" in entity.evidence[0]


# =========================================================================
# 2. Initial-to-Full Name Linkage
# =========================================================================

def test_unambiguous_initial_to_full_name(tmp_path, monkeypatch):
    """'R. Sharma' should link to 'Richa Sharma' when unambiguous."""
    monkeypatch.setattr("app.detectors.entity_resolver.get_safe_session_dir", lambda _: tmp_path)

    cands = [
        _make_candidate("c1", "Richa Sharma", start=10),
        _make_candidate("c2", "R. Sharma", start=90),
    ]

    resp = EntityResolver.resolve_entities("doc_test", cands, use_slm=False)
    assert resp.total_entities == 1
    entity = resp.entities[0]
    assert entity.canonical_name == "Richa Sharma"
    assert set(entity.candidate_ids) == {"c1", "c2"}
    assert set(entity.variants) == {"Richa Sharma", "R. Sharma"}
    assert any("Unambiguous initial match" in ev for ev in entity.evidence)


# =========================================================================
# 3. Title-Based Variant Linkage
# =========================================================================

def test_title_variant_linkage(tmp_path, monkeypatch):
    """'Ms. Sharma' should link to 'Richa Sharma' when unambiguous."""
    monkeypatch.setattr("app.detectors.entity_resolver.get_safe_session_dir", lambda _: tmp_path)

    cands = [
        _make_candidate("c1", "Richa Sharma", start=10),
        _make_candidate("c2", "Ms. Sharma", start=100),
    ]

    resp = EntityResolver.resolve_entities("doc_test", cands, use_slm=False)
    assert resp.total_entities == 1
    entity = resp.entities[0]
    assert entity.canonical_name == "Richa Sharma"
    assert set(entity.candidate_ids) == {"c1", "c2"}
    assert any("Title-variant match" in ev for ev in entity.evidence)


# =========================================================================
# 4. Ambiguous Initial Safeguard (J. Smith with John Smith & James Smith)
# =========================================================================

def test_ambiguous_initial_not_merged(tmp_path, monkeypatch):
    """'J. Smith' must NOT be auto-merged when both 'John Smith' and 'James Smith' exist."""
    monkeypatch.setattr("app.detectors.entity_resolver.get_safe_session_dir", lambda _: tmp_path)

    cands = [
        _make_candidate("c1", "John Smith", start=10),
        _make_candidate("c2", "James Smith", start=60),
        _make_candidate("c3", "J. Smith", start=120),
    ]

    resp = EntityResolver.resolve_entities("doc_test", cands, use_slm=False)
    # Must remain 3 separate entities
    assert resp.total_entities == 3

    j_smith = next(e for e in resp.entities if e.canonical_name == "J. Smith")
    assert j_smith.is_ambiguous is True
    assert any("Ambiguous initial" in ev for ev in j_smith.evidence)


# =========================================================================
# 5. Shared Surname Defense (Anil Kumar vs Sunil Kumar)
# =========================================================================

def test_shared_surname_not_merged(tmp_path, monkeypatch):
    """Employees sharing surname with different first names must NEVER be merged."""
    monkeypatch.setattr("app.detectors.entity_resolver.get_safe_session_dir", lambda _: tmp_path)

    cands = [
        _make_candidate("c1", "Anil Kumar", start=10),
        _make_candidate("c2", "Sunil Kumar", start=60),
        _make_candidate("c3", "Anil Sharma", start=120),
        _make_candidate("c4", "Sunil Sharma", start=180),
    ]

    resp = EntityResolver.resolve_entities("doc_test", cands, use_slm=False)
    assert resp.total_entities == 4
    names = {e.canonical_name for e in resp.entities}
    assert names == {"Anil Kumar", "Sunil Kumar", "Anil Sharma", "Sunil Sharma"}


# =========================================================================
# 6. Lexical Fuzzy Typo Matching (e.g. Swastik vs Swasthik)
# =========================================================================

def test_minor_typo_fuzzy_matching(tmp_path, monkeypatch):
    """Minor typo (>=88% similarity, same initial) should link with fuzzy evidence."""
    monkeypatch.setattr("app.detectors.entity_resolver.get_safe_session_dir", lambda _: tmp_path)

    cands = [
        _make_candidate("c1", "Swastik Phadke", start=10),
        _make_candidate("c2", "Swasthik Phadke", start=80),
    ]

    resp = EntityResolver.resolve_entities("doc_test", cands, use_slm=False)
    assert resp.total_entities == 1
    entity = resp.entities[0]
    assert set(entity.candidate_ids) == {"c1", "c2"}
    assert any("Fuzzy lexical similarity" in ev for ev in entity.evidence)


# =========================================================================
# 7. Local SLM Integration & Error Handling
# =========================================================================

def test_slm_malformed_json_handling():
    """SLM returning invalid JSON should be caught cleanly and return None."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": "{invalid:json, missing quotes"}

    with patch("httpx.Client.post", return_value=mock_resp):
        res = ModelService.analyze_context("Some text", ["Richa Sharma"])
        assert res is None


def test_slm_non_schema_json_handling():
    """SLM returning valid JSON that fails Pydantic validation should be discarded."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Missing required fields or wrong data types
    mock_resp.json.return_value = {"response": json.dumps({"unknown_key": 123})}

    with patch("httpx.Client.post", return_value=mock_resp):
        res = ModelService.analyze_context("Some text", ["Richa Sharma"])
        # Should parse with default empty lists or None without crashing
        assert isinstance(res, SLMAnalysisResponse)
        assert res.suggested_candidates == []
        assert res.suggested_links == []


def test_slm_timeout_handling():
    """SLM timing out should be caught cleanly and return None."""
    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Timeout")):
        res = ModelService.analyze_context("Some text", ["Richa Sharma"])
        assert res is None


def test_slm_unavailable_degraded_mode(tmp_path, monkeypatch):
    """When SLM connection fails, EntityResolver proceeds in degraded mode with warning."""
    monkeypatch.setattr("app.detectors.entity_resolver.get_safe_session_dir", lambda _: tmp_path)

    with patch("app.services.model_service.ModelService.check_availability", return_value=False):
        cands = [
            _make_candidate("c1", "Richa Sharma", start=10),
            _make_candidate("c2", "R. Sharma", start=80),
        ]
        resp = EntityResolver.resolve_entities("doc_test", cands, canonical_text="Richa Sharma and R. Sharma", use_slm=True)
        assert resp.degraded_mode is True
        assert resp.slm_available is False
        assert any("offline" in w.lower() for w in resp.warnings)
        # Rule-based linking still succeeded
        assert resp.total_entities == 1


# =========================================================================
# 8. Manual Link and Unlink Operations
# =========================================================================

def test_manual_link_and_unlink(tmp_path, monkeypatch):
    """User can manually link candidates into an entity, and unlink them into separate entities."""
    monkeypatch.setattr("app.detectors.entity_resolver.get_safe_session_dir", lambda _: tmp_path)

    cands = [
        _make_candidate("c1", "Anil Kumar", start=10),
        _make_candidate("c2", "A. K.", start=80),
    ]

    # Initial resolution yields 2 separate entities
    init_resp = EntityResolver.resolve_entities("doc_test", cands, use_slm=False)
    assert init_resp.total_entities == 2

    # 1. Manual Link
    link_resp = EntityResolver.link_candidates(
        document_id="doc_test",
        candidate_ids=["c1", "c2"],
        target_entity_id=init_resp.entities[0].entity_id,
    )
    assert link_resp.total_entities == 1
    assert set(link_resp.entities[0].candidate_ids) == {"c1", "c2"}
    assert link_resp.entities[0].is_user_defined is True

    # 2. Manual Unlink
    unlink_resp = EntityResolver.unlink_candidates(
        document_id="doc_test",
        candidate_ids=["c2"],
    )
    assert unlink_resp.total_entities == 2
    ent_a = next(e for e in unlink_resp.entities if "c1" in e.candidate_ids)
    ent_b = next(e for e in unlink_resp.entities if "c2" in e.candidate_ids)
    assert ent_a.entity_id != ent_b.entity_id


# =========================================================================
# 9. API Endpoints E2E Test
# =========================================================================

def test_entity_resolution_api_e2e():
    """Test full document upload -> detection -> entity resolution API lifecycle."""
    content = b"Candidate Richa Sharma signed the NDA. Later, R. Sharma approved the document."
    
    # 1. Upload document
    upload_res = client.post(
        "/api/documents/upload",
        files={"file": ("test_doc.txt", content, "text/plain")},
    )
    assert upload_res.status_code in [200, 201]
    doc_id = upload_res.json()["document_id"]

    try:
        # 2. Run detection
        det_res = client.post(f"/api/documents/{doc_id}/detect")
        assert det_res.status_code == 200
        candidates = det_res.json()["candidates"]
        assert len(candidates) >= 2

        # 3. Resolve entities
        resolve_res = client.post(f"/api/documents/{doc_id}/entities/resolve")
        assert resolve_res.status_code == 200
        group = resolve_res.json()
        assert group["total_entities"] >= 1
        
        # Verify candidate entity_id is assigned
        cand_res = client.get(f"/api/documents/{doc_id}/candidates")
        assert cand_res.status_code == 200
        all_cands = cand_res.json()
        for c in all_cands:
            assert c["entity_id"] is not None

        # 4. Get entities
        get_res = client.get(f"/api/documents/{doc_id}/entities")
        assert get_res.status_code == 200
        assert get_res.json()["total_entities"] == group["total_entities"]

        # 5. Manual link/unlink
        cand_ids = [c["candidate_id"] for c in all_cands[:2]]
        unlink_res = client.post(
            f"/api/documents/{doc_id}/entities/link",
            json={"candidate_ids": [cand_ids[0]], "action": "UNLINK"},
        )
        assert unlink_res.status_code == 200

    finally:
        # Cleanup
        client.delete(f"/api/documents/{doc_id}")
