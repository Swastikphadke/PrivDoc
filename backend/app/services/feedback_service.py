"""Feedback Service managing privacy-minimized audit events, encrypted aliases, and analysis proposals.

Strict Privacy Invariants:
1. NEVER log or persist raw document text, snippets, or raw candidate PII into SQLite.
2. NEVER silently retain alias values. Retaining alias values strictly requires explicit
   opt-in consent (`opt_in_consent=True`) and uses local AES-256-GCM encryption with automated retention.
3. Feedback collection NEVER mutates runtime regex patterns, model weights, or detection logic automatically.
   All feedback generates structured `FeedbackProposal` records for human engineering review.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.database.session import (
    delete_encrypted_aliases,
    delete_feedback_records,
    get_feedback_records,
    get_opt_in_encrypted_aliases,
    purge_expired_encrypted_aliases,
    record_feedback_event,
    record_opt_in_encrypted_alias,
)
from app.schemas.candidate import Candidate
from app.schemas.feedback import (
    FeedbackAction,
    FeedbackAnalysisReport,
    FeedbackProposal,
    FeedbackRecordSchema,
    OptInAliasRequest,
)

logger = logging.getLogger(__name__)

KEY_FILE_NAME = ".alias_encryption.key"


def _get_or_create_encryption_key() -> bytes:
    """Load or generate a local 256-bit AES-GCM key for opt-in encrypted aliases."""
    key_path = settings.DATA_DIR / KEY_FILE_NAME
    if key_path.exists():
        return key_path.read_bytes()
    
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    new_key = AESGCM.generate_key(bit_length=256)
    key_path.write_bytes(new_key)
    return new_key


class FeedbackService:
    """Orchestrates data-minimized feedback logging, opt-in alias storage, and proposal generation."""

    @classmethod
    def record_review_feedback(
        cls,
        document_id: str,
        candidate: Candidate,
        action: str,
        new_type: Optional[str] = None,
        scope: str = "OCCURRENCE",
    ) -> str:
        """Log review action feedback adhering strictly to data minimization."""
        action_enum = FeedbackAction.APPROVE if action == "APPROVED" else (
            FeedbackAction.REJECT if action == "REJECTED" else FeedbackAction.APPROVE
        )

        details: Dict[str, Any] = {
            "scope": scope,
            "original_type": candidate.type,
        }

        # If user changed category, record as CATEGORY_CHANGE with categorical metadata only
        if new_type and new_type.upper() != candidate.type:
            action_enum = FeedbackAction.CATEGORY_CHANGE
            details["new_type"] = new_type.upper()

        source_str = candidate.sources[0] if candidate.sources else "unknown"

        return record_feedback_event(
            doc_id=document_id,
            candidate_id=candidate.candidate_id,
            entity_id=candidate.entity_id,
            action=action_enum.value,
            candidate_type=candidate.type,
            source=source_str,
            confidence=candidate.confidence,
            details=json.dumps(details),
        )

    @classmethod
    def record_manual_add_feedback(
        cls,
        document_id: str,
        candidate: Candidate,
    ) -> str:
        """Log manual candidate addition adhering strictly to data minimization."""
        details: Dict[str, Any] = {
            "page_number": candidate.page_number,
            "span_length": candidate.end - candidate.start,
        }

        return record_feedback_event(
            doc_id=document_id,
            candidate_id=candidate.candidate_id,
            entity_id=candidate.entity_id,
            action=FeedbackAction.MANUAL_ADD.value,
            candidate_type=candidate.type,
            source="manual",
            confidence=1.0,
            details=json.dumps(details),
        )

    @classmethod
    def record_entity_action_feedback(
        cls,
        document_id: str,
        action: FeedbackAction,
        entity_id: Optional[str],
        entity_type: str,
        affected_count: int,
        details_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Log entity relationship operations (link, unlink, merge) without storing raw values."""
        meta = details_meta or {}
        meta["affected_count"] = affected_count

        return record_feedback_event(
            doc_id=document_id,
            candidate_id=None,
            entity_id=entity_id,
            action=action.value,
            candidate_type=entity_type,
            source="entity_resolver",
            confidence=1.0,
            details=json.dumps(meta),
        )

    # =========================================================================
    # Opt-In Encrypted Alias Mechanism
    # =========================================================================

    @classmethod
    def store_opt_in_alias(cls, req: OptInAliasRequest) -> str:
        """Store alias with explicit consent using AES-256-GCM encryption."""
        if not req.opt_in_consent:
            raise ValueError(
                "Consent violation: Explicit opt-in consent is required to retain encrypted alias."
            )

        if not req.alias_value or not req.alias_value.strip():
            raise ValueError("Alias value cannot be empty.")

        key = _get_or_create_encryption_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)

        data = req.alias_value.strip().encode("utf-8")
        associated_data = f"{req.document_id}:{req.entity_id}".encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, data, associated_data)

        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=req.retention_days)
        ).isoformat()

        return record_opt_in_encrypted_alias(
            doc_id=req.document_id,
            entity_id=req.entity_id,
            encrypted_alias=ciphertext,
            nonce=nonce,
            expires_at=expires_at,
        )

    @classmethod
    def get_opt_in_aliases(cls, document_id: str) -> List[Dict[str, str]]:
        """Retrieve and decrypt opt-in aliases for a document session."""
        purge_expired_encrypted_aliases()
        records = get_opt_in_encrypted_aliases(document_id)
        if not records:
            return []

        key = _get_or_create_encryption_key()
        aesgcm = AESGCM(key)
        results = []

        for rec in records:
            associated_data = f"{document_id}:{rec['entity_id']}".encode("utf-8")
            try:
                decrypted = aesgcm.decrypt(
                    rec["nonce"],
                    rec["encrypted_alias"],
                    associated_data
                ).decode("utf-8")
                results.append({
                    "id": rec["id"],
                    "entity_id": rec["entity_id"],
                    "alias_value": decrypted,
                    "created_at": rec.get("created_at"),
                    "expires_at": rec.get("expires_at"),
                })
            except Exception as e:
                logger.error("Failed to decrypt alias record %s: %s", rec["id"], e)

        return results

    @classmethod
    def clear_document_data(cls, document_id: str) -> None:
        """Purge all feedback and encrypted aliases for a document session."""
        delete_feedback_records(document_id)
        delete_encrypted_aliases(document_id)

    # =========================================================================
    # Controlled Feedback Analysis & Proposal Workflow
    # =========================================================================

    @classmethod
    def analyze_feedback(cls, document_id: Optional[str] = None) -> FeedbackAnalysisReport:
        """Aggregate feedback and synthesize rule tuning proposals.
        
        Invariant: Never automatically applies changes. Generates proposals for human review.
        """
        records = get_feedback_records(doc_id=document_id)
        total_events = len(records)

        action_counts: Dict[str, int] = {}
        category_rejections: Dict[str, int] = {}
        category_approvals: Dict[str, int] = {}
        source_rejections: Dict[str, int] = {}
        source_approvals: Dict[str, int] = {}
        manual_add_counts: Dict[str, int] = {}

        for rec in records:
            action = rec["action"]
            action_counts[action] = action_counts.get(action, 0) + 1
            cat = rec["candidate_type"]
            src = rec.get("source") or "unknown"

            if action == FeedbackAction.REJECT.value:
                category_rejections[cat] = category_rejections.get(cat, 0) + 1
                source_rejections[src] = source_rejections.get(src, 0) + 1
            elif action == FeedbackAction.APPROVE.value:
                category_approvals[cat] = category_approvals.get(cat, 0) + 1
                source_approvals[src] = source_approvals.get(src, 0) + 1
            elif action == FeedbackAction.MANUAL_ADD.value:
                manual_add_counts[cat] = manual_add_counts.get(cat, 0) + 1

        # Calculate rejection rates
        all_cats = set(category_rejections.keys()) | set(category_approvals.keys())
        cat_rates: Dict[str, float] = {}
        for c in all_cats:
            rejs = category_rejections.get(c, 0)
            apps = category_approvals.get(c, 0)
            total = rejs + apps
            cat_rates[c] = round(rejs / total, 4) if total > 0 else 0.0

        all_sources = set(source_rejections.keys()) | set(source_approvals.keys())
        src_rates: Dict[str, float] = {}
        for s in all_sources:
            rejs = source_rejections.get(s, 0)
            apps = source_approvals.get(s, 0)
            total = rejs + apps
            src_rates[s] = round(rejs / total, 4) if total > 0 else 0.0

        # Generate structured proposals
        proposals: List[FeedbackProposal] = []
        now_str = datetime.now(timezone.utc).isoformat()

        # Proposal 1: Check sources with high rejection rate (False Positives)
        for src, rate in src_rates.items():
            rejs = source_rejections.get(src, 0)
            apps = source_approvals.get(src, 0)
            if rejs >= 2 and rate >= 0.40:
                p = FeedbackProposal(
                    proposal_id=f"prop_{uuid.uuid4().hex[:8]}",
                    target_detector=src,
                    pii_type="ALL",
                    issue_type="HIGH_FALSE_POSITIVE_RATE",
                    description=(
                        f"Detector source '{src}' has a rejection rate of {rate*100:.1f}% "
                        f"({rejs} rejections out of {rejs + apps} decisions)."
                    ),
                    rejection_count=rejs,
                    approval_count=apps,
                    rejection_rate=rate,
                    recommended_action=(
                        f"Review and tighten pattern regexes or raise confidence threshold for detector '{src}'."
                    ),
                    status="PROPOSED",
                    created_at=now_str,
                )
                proposals.append(p)

        # Proposal 2: Check categories with recurring manual additions (False Negatives)
        for cat, count in manual_add_counts.items():
            if count >= 2:
                p = FeedbackProposal(
                    proposal_id=f"prop_{uuid.uuid4().hex[:8]}",
                    target_detector="pattern_library",
                    pii_type=cat,
                    issue_type="FALSE_NEGATIVE_PATTERN",
                    description=(
                        f"Detected {count} manual additions for category '{cat}', indicating gaps "
                        "in automated detection coverage."
                    ),
                    rejection_count=0,
                    approval_count=count,
                    rejection_rate=0.0,
                    recommended_action=(
                        f"Expand pattern test fixtures and regex patterns for category '{cat}'."
                    ),
                    status="PROPOSED",
                    created_at=now_str,
                )
                proposals.append(p)

        return FeedbackAnalysisReport(
            total_feedback_events=total_events,
            action_counts=action_counts,
            category_rejection_rates=cat_rates,
            source_rejection_rates=src_rates,
            proposals=proposals,
            human_approval_required=True,
        )
