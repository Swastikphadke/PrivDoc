"""Pydantic schemas for Entity Resolution, Clustering, and SLM Integration."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EntityLinkAction(str, Enum):
    LINK = "LINK"
    UNLINK = "UNLINK"
    MERGE = "MERGE"


class ResolutionTier(str, Enum):
    EXACT = "EXACT"
    DETERMINISTIC_VARIANT = "DETERMINISTIC_VARIANT"
    PROBABLE_HEURISTIC = "PROBABLE_HEURISTIC"
    AMBIGUOUS_CONFLICT = "AMBIGUOUS_CONFLICT"
    USER_DEFINED = "USER_DEFINED"


class EntityLinkReason(BaseModel):
    """Structured explanation record for why two surface mentions were linked or kept separate."""
    rule: str = Field(..., description="Rule identifier (e.g. EXACT_NORMALIZED, UNAMBIGUOUS_INITIAL, PHONETIC_TYPO_SIMILARITY)")
    source_variant: str = Field(..., description="Source surface mention")
    target_variant: str = Field(..., description="Target canonical/anchor mention")
    score: float = Field(default=1.0, ge=0.0, le=1.0, description="Heuristic evidence score for this link")
    explanation: str = Field(..., description="Human-readable explanation of the linkage evidence")


class Entity(BaseModel):
    """Represents a resolved cluster of candidate occurrences belonging to the same entity."""
    entity_id: str = Field(..., description="Unique entity cluster identifier (e.g. ent_1)")
    canonical_name: str = Field(..., description="Chosen canonical/representative name for the entity")
    entity_type: str = Field(..., description="PII category: PERSON, ID_LIKE, EMAIL, PHONE, ADDRESS")
    candidate_ids: List[str] = Field(default_factory=list, description="IDs of candidates belonging to this entity")
    variants: List[str] = Field(default_factory=list, description="Distinct surface text representations")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall cluster confidence score")
    resolution_tier: str = Field(default=ResolutionTier.EXACT.value, description="Resolution confidence tier")
    evidence: List[str] = Field(default_factory=list, description="Deterministic and heuristic evidence strings")
    link_reasons: List[EntityLinkReason] = Field(default_factory=list, description="Structured link explanation objects")
    suggested_links: List[EntityLinkReason] = Field(default_factory=list, description="Non-merged borderline link suggestions for human review")
    normalized_value: Optional[str] = Field(default=None, description="Category-normalized representation within the document")
    is_ambiguous: bool = Field(default=False, description="True if potential conflicting links were detected")
    is_user_defined: bool = Field(default=False, description="True if manually grouped or edited by the user")


class EntityLinkRequest(BaseModel):
    """Payload to manually link, unlink, or merge entity occurrences."""
    candidate_ids: List[str] = Field(..., min_length=1, description="Candidate IDs to act upon")
    target_entity_id: Optional[str] = Field(default=None, description="Target entity ID to link to")
    action: EntityLinkAction = Field(default=EntityLinkAction.LINK, description="Action: LINK, UNLINK, or MERGE")


class EntityGroupResponse(BaseModel):
    """Response containing all resolved entity clusters for a document."""
    document_id: str = Field(..., description="Associated document session identifier")
    total_entities: int = Field(..., description="Count of resolved entity clusters")
    entities: List[Entity] = Field(default_factory=list, description="List of resolved entity clusters")
    degraded_mode: bool = Field(default=False, description="True if SLM was unavailable and resolution operated in degraded mode")
    slm_available: bool = Field(default=False, description="Whether the local SLM runtime was available")
    warnings: List[str] = Field(default_factory=list, description="Operational warnings or fallback disclosures")


# =========================================================================
# Structured SLM Response Schemas
# =========================================================================

class SLMSuggestedCandidate(BaseModel):
    """Structured proposal from local SLM for potentially missed or ambiguous PII."""
    text: str = Field(..., description="Exact entity text observed")
    type: str = Field(..., description="PII category (PERSON, EMAIL, etc.)")
    reason: str = Field(..., description="Justification for why this span is PII")
    estimated_start: Optional[int] = Field(default=None, description="Estimated start offset if known")
    estimated_end: Optional[int] = Field(default=None, description="Estimated end offset if known")


class SLMSuggestedLink(BaseModel):
    """Structured proposal from local SLM for name variant / alias linkage."""
    source_text: str = Field(..., description="First entity mention")
    target_text: str = Field(..., description="Second entity mention")
    relation_type: str = Field(..., description="Relation: VARIANT, INITIAL, TITLE, NICKNAME, ALIAS")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Confidence in the linkage")
    reason: str = Field(..., description="Linguistic explanation")


class SLMAnalysisResponse(BaseModel):
    """Strict JSON schema required from local SLM contextual analysis."""
    suggested_candidates: List[SLMSuggestedCandidate] = Field(
        default_factory=list, description="Candidate suggestions for missed PII"
    )
    suggested_links: List[SLMSuggestedLink] = Field(
        default_factory=list, description="Suggestions for linking entity variants"
    )
    notes: Optional[str] = Field(default=None, description="General contextual analysis observations")
