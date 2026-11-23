"""Pydantic schemas for PII Candidates, Detection Results, and Review Statuses."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class PIICategory(str, Enum):
    PERSON = "PERSON"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    ADDRESS = "ADDRESS"
    ID_LIKE = "ID_LIKE"


class ConfidenceBand(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MANUAL = "MANUAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class Candidate(BaseModel):
    """Normalized PII candidate span with transparent heuristic provenance."""
    candidate_id: str = Field(..., description="Unique candidate identifier")
    document_id: str = Field(..., description="Associated document session identifier")
    start: int = Field(..., description="Inclusive start character offset in canonical text")
    end: int = Field(..., description="Exclusive end character offset in canonical text")
    text: str = Field(..., description="Exact matched string from canonical text")
    type: str = Field(..., description="PII category: PERSON, EMAIL, PHONE, ADDRESS, ID_LIKE")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Heuristic evidence score [0.0, 1.0] (uncalibrated)")
    confidence_band: str = Field(default="HIGH", description="HIGH, MEDIUM, or LOW")
    confidence_type: str = Field(
        default="HEURISTIC_EVIDENCE",
        description="Score basis: HEURISTIC_EVIDENCE (rule/context weighted, not calibrated probability)",
    )
    sources: List[str] = Field(default_factory=list, description="Detector provenance, e.g. ['regex', 'ner']")
    explanation: List[str] = Field(
        default_factory=list,
        description="Human-readable explanation of why this candidate was detected",
    )
    context_signals: List[str] = Field(
        default_factory=list,
        description="Supporting contextual cues observed near the candidate span",
    )
    detector_agreement: str = Field(
        default="SINGLE_SOURCE",
        description="Agreement status: SINGLE_SOURCE, MULTI_DETECTOR_CONSENSUS, or TYPE_CONFLICT",
    )
    is_ambiguous_suggestion: bool = Field(
        default=False,
        description="True if candidate is an ambiguous suggestion requiring explicit human confirmation",
    )
    page_number: Optional[int] = Field(default=None, description="PDF page number (1-indexed) if applicable")
    bbox: Optional[List[float]] = Field(default=None, description="[x0, y0, x1, y1] bounding box if applicable")
    review_status: str = Field(default="PENDING", description="Human review decision")
    entity_id: Optional[str] = Field(default=None, description="Associated entity cluster identifier")


class DetectionResponse(BaseModel):
    """Response payload for document detection."""
    document_id: str
    total_candidates: int
    candidates: List[Candidate]
    execution_time_ms: float
    detectors_run: List[str]
