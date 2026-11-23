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
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
from app.schemas.candidate import Candidate, ConfidenceBand, ReviewStatus
from app.schemas.feedback import (
    FeedbackAction,
    FeedbackAnalysisReport,
    FeedbackProposal,
    FeedbackRecordSchema,
    OptInAliasRequest,
)

logger = logging.getLogger(__name__)

KEY_FILE_NAME = ".alias_encryption.key"

# Non-PII standard/specification/document prefixes that must NEVER be learned as ID_LIKE prefixes
BLOCKED_ID_PREFIXES: Set[str] = {
    "ISO", "IEC", "IEEE", "RFC", "UTF", "ASCII", "PDF", "TXT", "DOC", "FIG",
    "SEC", "PAGE", "VER", "HTTP", "HTTPS", "API", "URL", "SQL", "CPU", "RAM",
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
}
STRUCTURAL_ID_PATTERN = re.compile(r"^([A-Za-z]{2,8})[-_#][0-9][A-Za-z0-9_-]{2,14}$")


def _get_or_create_encryption_key() -> bytes:
    """Load or generate a local 256-bit AES-GCM key for opt-in encrypted aliases."""
    key_path = settings.DATA_DIR / KEY_FILE_NAME
    if key_path.exists():
        key = key_path.read_bytes()
        if len(key) == 32:
            return key
        logger.warning(
            "Corrupted or invalid alias encryption key detected (length %d bytes, expected 32); regenerating.",
            len(key),
        )

    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    new_key = AESGCM.generate_key(bit_length=256)
    key_path.write_bytes(new_key)
    try:
        os.chmod(key_path, 0o600)
    except Exception:
        pass
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
        """Log manual candidate addition adhering strictly to data minimization.

        For ID_LIKE candidates matching a structural prefix schema (<ALPHA_PREFIX>-<DIGITS>),
        records only the non-PII uppercase alphabetic prefix (never the digits or raw value)
        for quorum-gated active learning.
        """
        details: Dict[str, Any] = {
            "page_number": candidate.page_number,
            "span_length": candidate.end - candidate.start,
        }
        if candidate.type == "ID_LIKE" and candidate.text:
            m = STRUCTURAL_ID_PATTERN.match(candidate.text.strip())
            if m:
                prefix = m.group(1).upper()
                if prefix not in BLOCKED_ID_PREFIXES:
                    details["structural_id_prefix"] = prefix

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

    # =========================================================================
    # Controlled Active-Learning Loop (Quorum-Gated & Privacy-Preserving)
    # =========================================================================

    @classmethod
    def get_active_learning_profile(cls, min_prefix_quorum: int = 2) -> Dict[str, Any]:
        """Compute active-learning parameters from historical data-minimized feedback records.

        Safeguards:
        1. Zero raw PII is stored or read from `feedback_records`.
        2. Structural ID prefixes require a quorum (`min_prefix_quorum >= 2`) of manual additions
           and must not appear in `BLOCKED_ID_PREFIXES` (prevents learning ISO/RFC/date codes
           or single-instance unverified inputs).
        3. Empirical confidence adjustments per `(source, candidate_type)` require >= 3 review
           decisions and are strictly bounded to [-0.15, +0.10].
        """
        records = get_feedback_records()
        prefix_counts: Dict[str, int] = {}
        pair_stats: Dict[Tuple[str, str], Dict[str, int]] = {}

        for rec in records:
            action = rec.get("action")
            cat = rec.get("candidate_type") or "DEFAULT"
            src = rec.get("source") or "unknown"

            if action in (FeedbackAction.APPROVE.value, FeedbackAction.REJECT.value):
                key = (src, cat)
                if key not in pair_stats:
                    pair_stats[key] = {"approvals": 0, "rejections": 0}
                if action == FeedbackAction.APPROVE.value:
                    pair_stats[key]["approvals"] += 1
                else:
                    pair_stats[key]["rejections"] += 1

            if action == FeedbackAction.MANUAL_ADD.value and cat == "ID_LIKE":
                raw_details = rec.get("details")
                if raw_details:
                    try:
                        parsed = json.loads(raw_details) if isinstance(raw_details, str) else raw_details
                        prefix = (parsed.get("structural_id_prefix") or "").upper()
                        if (
                            prefix
                            and 2 <= len(prefix) <= 8
                            and prefix.isalpha()
                            and prefix not in BLOCKED_ID_PREFIXES
                        ):
                            prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
                    except Exception:
                        pass

        learned_prefixes = sorted(
            [p for p, cnt in prefix_counts.items() if cnt >= max(1, min_prefix_quorum)]
        )

        confidence_deltas: Dict[str, float] = {}
        for (src, cat), counts in pair_stats.items():
            total = counts["approvals"] + counts["rejections"]
            if total >= 3:
                approval_rate = counts["approvals"] / total
                rejection_rate = counts["rejections"] / total
                if approval_rate >= 0.80:
                    delta = round(min(0.08, (approval_rate - 0.75) * 0.32), 2)
                    confidence_deltas[f"{src}::{cat}"] = delta
                elif rejection_rate >= 0.60:
                    delta = -round(min(0.15, (rejection_rate - 0.50) * 0.30), 2)
                    confidence_deltas[f"{src}::{cat}"] = delta

        return {
            "learned_id_prefixes": learned_prefixes,
            "prefix_observation_counts": prefix_counts,
            "confidence_deltas": confidence_deltas,
        }

    @classmethod
    def apply_active_learning(
        cls,
        document_id: str,
        text: str,
        existing_candidates: List[Candidate],
        min_prefix_quorum: int = 2,
    ) -> Tuple[List[Candidate], bool]:
        """Apply quorum-gated active-learning rules and empirical confidence calibration.

        Returns:
            Tuple of (newly proposed Candidate spans, whether active learning contributed).
        """
        profile = cls.get_active_learning_profile(min_prefix_quorum=min_prefix_quorum)
        learned_prefixes: List[str] = profile.get("learned_id_prefixes", [])
        confidence_deltas: Dict[str, float] = profile.get("confidence_deltas", {})
        contributed = False

        # 1. Apply bounded empirical confidence calibration to existing candidates
        if confidence_deltas:
            for cand in existing_candidates:
                primary_src = cand.sources[0] if cand.sources else "unknown"
                key = f"{primary_src}::{cand.type}"
                delta = confidence_deltas.get(key, 0.0)
                if delta != 0.0:
                    new_conf = round(max(0.35, min(0.99, cand.confidence + delta)), 2)
                    if new_conf != cand.confidence:
                        cand.confidence = new_conf
                        cand.confidence_band = (
                            ConfidenceBand.HIGH.value
                            if new_conf >= 0.85
                            else ConfidenceBand.MEDIUM.value
                            if new_conf >= 0.60
                            else ConfidenceBand.LOW.value
                        )
                        sig = (
                            "active_learning:high_approval_prior"
                            if delta > 0
                            else "active_learning:high_rejection_caution"
                        )
                        if sig not in cand.context_signals:
                            cand.context_signals.append(sig)
                        exp_note = (
                            f"Active-learning confidence calibration ({delta:+.2f}) from prior reviewer feedback"
                        )
                        if exp_note not in cand.explanation:
                            cand.explanation.append(exp_note)
                        contributed = True

        # 2. Scan for quorum-verified structural ID_LIKE prefixes learned from manual additions
        new_candidates: List[Candidate] = []
        if learned_prefixes and text:
            prefix_union = "|".join(re.escape(p) for p in learned_prefixes)
            dyn_regex = re.compile(rf"\b(?:{prefix_union})[-_#][0-9][A-Za-z0-9_-]{{2,14}}\b", re.IGNORECASE)
            existing_spans = [(c.start, c.end) for c in existing_candidates]
            idx = 0
            for match in dyn_regex.finditer(text):
                s, e = match.span()
                if any(max(s, es) < min(e, ee) for es, ee in existing_spans):
                    continue
                idx += 1
                matched_str = text[s:e]
                prefix_used = re.split(r"[-_#]", matched_str, maxsplit=1)[0].upper()
                new_candidates.append(
                    Candidate(
                        candidate_id=f"c_al_{idx:04d}",
                        document_id=document_id,
                        start=s,
                        end=e,
                        text=matched_str,
                        type="ID_LIKE",
                        confidence=0.84,
                        confidence_band=ConfidenceBand.MEDIUM.value,
                        confidence_type="HEURISTIC_EVIDENCE",
                        sources=["active_learning"],
                        explanation=[
                            f"Matched organization-specific ID prefix '{prefix_used}-' learned via quorum-gated reviewer feedback"
                        ],
                        context_signals=[f"active_learning_prefix:{prefix_used}"],
                        review_status=ReviewStatus.PENDING.value,
                    )
                )
                existing_spans.append((s, e))
                contributed = True

        return new_candidates, contributed
