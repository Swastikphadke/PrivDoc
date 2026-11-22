"""SLM Contextual Detector for PrivyDoc.

Uses local SLM to discover ambiguous entities and assist in context classification.
All SLM outputs are strictly validated, treated as untrusted suggestions, and never
auto-approved or used to bypass deterministic rules.
"""

import re
import uuid
from typing import List, Tuple
from app.schemas.candidate import Candidate, ConfidenceBand, ReviewStatus
from app.schemas.entity import SLMAnalysisResponse
from app.services.model_service import ModelService


class SLMDetector:
    """Wrapper for local SLM contextual analysis and candidate proposal."""

    @classmethod
    def detect_and_suggest(
        cls,
        document_id: str,
        canonical_text: str,
        existing_candidates: List[Candidate],
    ) -> Tuple[List[Candidate], SLMAnalysisResponse]:
        """Call local SLM for contextual review and propose new candidate spans if found.
        
        Returns:
            Tuple of (newly suggested Candidates, SLMAnalysisResponse or empty response)
        """
        person_names = [c.text for c in existing_candidates if c.type == "PERSON"]
        
        slm_result = ModelService.analyze_context(canonical_text, person_names)
        if not slm_result:
            return [], SLMAnalysisResponse()

        suggested_candidates: List[Candidate] = []
        existing_spans = {(c.start, c.end) for c in existing_candidates}

        for suggestion in slm_result.suggested_candidates:
            target_text = suggestion.text.strip()
            if not target_text or len(target_text) < 2:
                continue

            # Find occurrences of target_text in canonical text
            pattern = re.escape(target_text)
            for match in re.finditer(pattern, canonical_text):
                start, end = match.span()
                # Check if already covered by an existing candidate
                overlap = any(
                    max(start, ex_start) < min(end, ex_end)
                    for (ex_start, ex_end) in existing_spans
                )
                if not overlap:
                    candidate = Candidate(
                        candidate_id=f"cand_slm_{uuid.uuid4().hex[:8]}",
                        document_id=document_id,
                        start=start,
                        end=end,
                        text=canonical_text[start:end],
                        type=suggestion.type.upper() if suggestion.type else "PERSON",
                        confidence=0.60,
                        confidence_band=ConfidenceBand.MEDIUM.value,
                        sources=["slm"],
                        review_status=ReviewStatus.PENDING.value,
                    )
                    suggested_candidates.append(candidate)
                    existing_spans.add((start, end))

        return suggested_candidates, slm_result
