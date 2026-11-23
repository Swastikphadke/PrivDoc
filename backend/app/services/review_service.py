"""Review Service managing human review actions, manual candidate additions, and state persistence.

Implements Stage 6 of the PrivyDoc processing pipeline:
- Approves, rejects, or reverts candidates to PENDING.
- Supports category changes.
- Supports bulk decisions for linked entity occurrences.
- Supports 'redact all similar' for exact normalized text matches.
- Supports manual candidate creation from arbitrary text selections.
- Stores decisions in SQLite metadata without storing raw document text.
"""

import json
import uuid
from pathlib import Path
from typing import List, Optional
from app.core.security import atomic_write_text, get_safe_session_dir
from app.database.session import record_review_decision, update_document_status
from app.detectors.entity_resolver import EntityResolver
from app.schemas.candidate import Candidate, ConfidenceBand, ReviewStatus
from app.schemas.review import (
    ManualCandidateRequest,
    ReviewActionRequest,
    ReviewDecisionAction,
    ReviewSummaryResponse,
)
from app.services.detection_service import DetectionService
from app.services.feedback_service import FeedbackService


class ReviewService:
    """Orchestrates human review operations and candidate mutations."""

    @classmethod
    def submit_review(
        cls,
        document_id: str,
        action: ReviewActionRequest,
    ) -> ReviewSummaryResponse:
        """Apply a review decision (APPROVE, REJECT, PENDING/UNDO) to candidates."""
        candidates = EntityResolver.load_candidates(document_id)
        if not candidates:
            raise ValueError(f"No candidates found for document session '{document_id}'.")

        target = next((c for c in candidates if c.candidate_id == action.candidate_id), None)
        if not target:
            raise ValueError(f"Candidate '{action.candidate_id}' not found.")

        # Determine target candidates scope
        affected: List[Candidate] = [target]
        scope = "OCCURRENCE"

        if action.apply_to_linked and target.entity_id:
            scope = "LINKED_GROUP"
            affected = [c for c in candidates if c.entity_id == target.entity_id]
        elif action.apply_to_similar:
            scope = "SIMILAR_TEXT"
            target_norm = target.text.strip().casefold()
            affected = [c for c in candidates if c.text.strip().casefold() == target_norm]

        # Determine new status
        if action.decision == ReviewDecisionAction.APPROVE:
            new_status = ReviewStatus.APPROVED.value
        elif action.decision == ReviewDecisionAction.REJECT:
            new_status = ReviewStatus.REJECTED.value
        else:
            new_status = ReviewStatus.PENDING.value

        for cand in affected:
            cand.review_status = new_status
            if action.new_type:
                cand.type = action.new_type.upper()

            # Record in SQLite audit log
            record_review_decision(
                doc_id=document_id,
                cand_id=cand.candidate_id,
                decision=new_status,
                scope=scope,
            )
            # Record data-minimized feedback event
            FeedbackService.record_review_feedback(
                document_id=document_id,
                candidate=cand,
                action=new_status,
                new_type=action.new_type if action.new_type else None,
                scope=scope,
            )

        # Save mutated candidates atomically
        session_dir = get_safe_session_dir(document_id)
        cands_path = session_dir / "candidates.json"
        cands_data = [c.model_dump() for c in candidates]
        atomic_write_text(cands_path, json.dumps(cands_data, indent=2), encoding="utf-8")

        # Invalidate any stale export or summary artifacts (TDR-018)
        cls._invalidate_stale_exports_and_summaries(document_id, session_dir)

        return cls._build_summary(document_id, candidates)

    @classmethod
    def add_manual_candidate(
        cls,
        document_id: str,
        req: ManualCandidateRequest,
    ) -> Candidate:
        """Create a manual candidate span from user selection."""
        session_dir = get_safe_session_dir(document_id)
        canonical_path = session_dir / "canonical.txt"
        if not canonical_path.exists():
            raise FileNotFoundError(f"Canonical text not found for session '{document_id}'.")

        canonical_text = canonical_path.read_text(encoding="utf-8")
        text_len = len(canonical_text)

        if req.start < 0 or req.end > text_len or req.start >= req.end:
            raise ValueError(
                f"Invalid selection span [{req.start}, {req.end}) for canonical text length {text_len}."
            )

        matched_text = canonical_text[req.start:req.end]
        if not matched_text.strip():
            raise ValueError("Manual redaction span cannot be empty or purely whitespace.")

        candidates = EntityResolver.load_candidates(document_id)

        # Build manual candidate
        cand_id = f"c_man_{uuid.uuid4().hex[:8]}"
        manual_cand = Candidate(
            candidate_id=cand_id,
            document_id=document_id,
            start=req.start,
            end=req.end,
            text=matched_text,
            type=req.type.upper(),
            confidence=1.0,
            confidence_band=ConfidenceBand.HIGH.value,
            sources=["manual"],
            page_number=req.page_number,
            bbox=req.bbox,
            review_status=ReviewStatus.APPROVED.value,  # Manual selections are auto-approved by human
        )

        # Enrich PDF page_number and bbox from coordinates.json if not explicitly supplied
        coords_path = session_dir / "coordinates.json"
        if (manual_cand.bbox is None or manual_cand.page_number is None) and coords_path.exists():
            DetectionService._enrich_coordinates([manual_cand], coords_path)

        candidates.append(manual_cand)
        candidates.sort(key=lambda c: (c.start, -(c.end - c.start)))

        # Update entity clustering with the new candidate
        EntityResolver.resolve_entities(
            document_id=document_id,
            candidates=candidates,
            canonical_text=canonical_text,
            use_slm=False,
        )

        # Record in SQLite audit log
        record_review_decision(
            doc_id=document_id,
            cand_id=cand_id,
            decision=ReviewStatus.APPROVED.value,
            scope="MANUAL",
        )

        # Record data-minimized feedback event
        FeedbackService.record_manual_add_feedback(
            document_id=document_id,
            candidate=manual_cand,
        )

        # Invalidate any stale export or summary artifacts (TDR-018)
        cls._invalidate_stale_exports_and_summaries(document_id, session_dir)

        return manual_cand

    @classmethod
    def _invalidate_stale_exports_and_summaries(cls, document_id: str, session_dir: Path) -> None:
        """Purge export and summary artifacts when review decisions change (TDR-018).
        
        Ensures that stale verified exports or summaries cannot be accessed after
        candidates or review statuses are mutated.
        """
        for filename in ["export_metadata.json", "sanitized.txt", "sanitized.pdf", "summary.json"]:
            artifact_path = session_dir / filename
            if artifact_path.exists():
                try:
                    artifact_path.unlink()
                except Exception:
                    pass
        update_document_status(document_id, "REVIEWING")

    @classmethod
    def get_review_summary(cls, document_id: str) -> ReviewSummaryResponse:
        """Generate review progress statistics for the document."""
        candidates = EntityResolver.load_candidates(document_id)
        return cls._build_summary(document_id, candidates)

    @classmethod
    def _build_summary(cls, document_id: str, candidates: List[Candidate]) -> ReviewSummaryResponse:
        total = len(candidates)
        approved = sum(1 for c in candidates if c.review_status == ReviewStatus.APPROVED.value)
        rejected = sum(1 for c in candidates if c.review_status == ReviewStatus.REJECTED.value)
        pending = sum(
            1 for c in candidates if c.review_status in (ReviewStatus.PENDING.value, ReviewStatus.NEEDS_REVIEW.value)
        )
        manual = sum(1 for c in candidates if "manual" in c.sources)

        return ReviewSummaryResponse(
            document_id=document_id,
            total_candidates=total,
            approved_count=approved,
            rejected_count=rejected,
            pending_count=pending,
            manual_count=manual,
            candidates=candidates,
        )
