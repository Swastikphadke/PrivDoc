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
        valid_categories = {"PERSON", "EMAIL", "PHONE", "ADDRESS", "ID_LIKE"}

        for suggestion in slm_result.suggested_candidates:
            target_text = suggestion.text.strip()
            if not target_text or len(target_text) < 2:
                continue

            sug_type = suggestion.type.upper() if suggestion.type else "PERSON"
            if sug_type not in valid_categories:
                sug_type = "PERSON"
            reason_str = (
                f"SLM contextual assistance: {suggestion.reason.strip()}"
                if suggestion.reason and suggestion.reason.strip()
                else f"SLM contextual detection for {sug_type}"
            )

            # Find occurrences of target_text in canonical text and emit for merge_candidates
            # (Overlapping same-type spans will be merged into MULTI_DETECTOR_CONSENSUS by DetectionService;
            # conflicting types will be marked TYPE_CONFLICT; novel spans remain PENDING at confidence 0.65)
            pattern = re.escape(target_text)
            for match in re.finditer(pattern, canonical_text):
                start, end = match.span()
                candidate = Candidate(
                    candidate_id=f"cand_slm_{uuid.uuid4().hex[:8]}",
                    document_id=document_id,
                    start=start,
                    end=end,
                    text=canonical_text[start:end],
                    type=sug_type,
                    confidence=0.65,
                    confidence_band=ConfidenceBand.MEDIUM.value,
                    confidence_type="HEURISTIC_EVIDENCE",
                    sources=["slm"],
                    explanation=[reason_str],
                    context_signals=["slm_contextual_assistance"],
                    review_status=ReviewStatus.PENDING.value,
                )
                suggested_candidates.append(candidate)

        return suggested_candidates, slm_result
