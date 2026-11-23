"""Pydantic schemas for Privacy-Preserving Local Feedback & Analysis.

Strict Privacy Invariant:
Feedback records must NEVER contain raw document text, snippets, or raw candidate PII.
Only pseudonymous identifiers, PII categories, detector provenance, confidence, and
action types are stored.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FeedbackAction(str, Enum):
    """Enumeration of human feedback action types."""
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    MANUAL_ADD = "MANUAL_ADD"
    CATEGORY_CHANGE = "CATEGORY_CHANGE"
    LINK_ENTITIES = "LINK_ENTITIES"
    UNLINK_ENTITIES = "UNLINK_ENTITIES"
    MERGE_ENTITIES = "MERGE_ENTITIES"


class FeedbackRecordSchema(BaseModel):
    """Data-minimized representation of a logged feedback event."""
    id: str
    document_id: str
    candidate_id: Optional[str] = None
    entity_id: Optional[str] = None
    action: FeedbackAction
    candidate_type: str
    source: Optional[str] = None
    confidence: Optional[float] = None
    details: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


class OptInAliasRequest(BaseModel):
    """Explicit opt-in request for local encrypted alias retention."""
    document_id: str
    entity_id: str
    alias_value: str
    opt_in_consent: bool = Field(
        default=False,
        description="Explicit user consent must be True to retain encrypted alias."
    )
    retention_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Retention lifetime in days before automated purging."
    )


class FeedbackProposal(BaseModel):
    """Structured rule modification recommendation generated from aggregated feedback.
    
    Must undergo human developer review and evaluation before any code adoption.
    NEVER automatically applied at runtime.
    """
    proposal_id: str
    target_detector: str
    pii_type: str
    issue_type: str
    description: str
    rejection_count: int
    approval_count: int
    rejection_rate: float
    recommended_action: str
    status: str = "PROPOSED"
    created_at: str


class FeedbackAnalysisReport(BaseModel):
    """Aggregated analysis report summarizing user feedback and potential tuning points."""
    total_feedback_events: int
    action_counts: Dict[str, int]
    category_rejection_rates: Dict[str, float]
    source_rejection_rates: Dict[str, float]
    proposals: List[FeedbackProposal]
    human_approval_required: bool = True
