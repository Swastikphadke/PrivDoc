"""Pydantic schemas for Human Review Actions, Decisions, and Manual Spans."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

from app.schemas.candidate import Candidate


class ReviewDecisionAction(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    PENDING = "PENDING"  # Undo action


class ReviewActionRequest(BaseModel):
    """Payload to approve, reject, or undo a candidate, optionally applying to linked/similar matches."""
    candidate_id: str = Field(..., description="Target candidate identifier")
    decision: ReviewDecisionAction = Field(..., description="Decision action: APPROVE, REJECT, or PENDING")
    new_type: Optional[str] = Field(default=None, description="Optional new PII category (PERSON, EMAIL, etc.)")
    apply_to_linked: bool = Field(default=False, description="Apply decision to all occurrences linked to the same entity")
    apply_to_similar: bool = Field(default=False, description="Apply decision to all occurrences with matching normalized text")


class ManualCandidateRequest(BaseModel):
    """Payload to create a manual redaction candidate span from user text selection."""
    start: int = Field(..., ge=0, description="Inclusive start offset in canonical text")
    end: int = Field(..., ge=1, description="Exclusive end offset in canonical text")
    type: str = Field(default="PERSON", description="PII category: PERSON, EMAIL, PHONE, ADDRESS, ID_LIKE")
    page_number: Optional[int] = Field(default=None, description="PDF page number (1-indexed) if applicable")
    bbox: Optional[List[float]] = Field(default=None, description="PDF bounding box [x0, y0, x1, y1] if applicable")


class ReviewSummaryResponse(BaseModel):
    """Statistical overview of human review decisions for the document session."""
    document_id: str
    total_candidates: int
    approved_count: int
    rejected_count: int
    pending_count: int
    manual_count: int
    candidates: List[Candidate]
