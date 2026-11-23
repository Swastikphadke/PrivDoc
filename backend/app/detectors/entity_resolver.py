"""Deterministic and Contextual Entity Resolution Engine for PrivyDoc.

Implements Stage 5 of the processing pipeline:
1. Exact normalized matching (case-insensitive, whitespace normalized).
2. Unambiguous initial-to-surname matching (R. Sharma -> Richa Sharma).
3. Ambiguity defense (J. Smith with John Smith and James Smith is flagged, NOT auto-merged).
4. Surname-sharing defense (Anil Kumar vs Sunil Kumar are NEVER merged).
5. Title-to-full-name variant matching (Ms. Sharma -> Richa Sharma).
6. Lexical fuzzy similarity proposals (RapidFuzz >= 85%) for minor typos.
7. Local SLM corroborating evidence integration.
8. Manual user linking, unlinking, and merging operations.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from rapidfuzz import fuzz

from app.core.security import get_safe_session_dir
from app.schemas.candidate import Candidate
from app.schemas.entity import Entity, EntityGroupResponse, EntityLinkAction, SLMAnalysisResponse
from app.schemas.feedback import FeedbackAction
from app.services.feedback_service import FeedbackService
from app.services.model_service import ModelService

logger = logging.getLogger(__name__)

TITLES: Set[str] = {
    "dr", "dr.", "mr", "mr.", "ms", "ms.", "mrs", "mrs.",
    "prof", "prof.", "shri", "smt", "rev", "rev."
}


class NameComponents:
    """Helper to parse and extract person name components."""

    def __init__(self, raw_text: str):
        self.raw = raw_text.strip()
        tokens = [t for t in self.raw.split() if t]
        
        self.title: Optional[str] = None
        if tokens and tokens[0].lower() in TITLES:
            self.title = tokens[0]
            tokens = tokens[1:]

        self.tokens = tokens
        self.first_name: Optional[str] = tokens[0] if len(tokens) >= 1 else None
        self.last_name: Optional[str] = tokens[-1] if len(tokens) >= 2 else None
        
        # Check initial representations
        self.is_first_initial: bool = False
        self.first_initial_char: Optional[str] = None
        if self.first_name:
            clean_first = self.first_name.rstrip(".")
            if len(clean_first) == 1 and clean_first.isalpha():
                self.is_first_initial = True
                self.first_initial_char = clean_first.upper()
            else:
                self.first_initial_char = clean_first[0].upper()

        self.is_last_initial: bool = False
        self.last_initial_char: Optional[str] = None
        if self.last_name:
            clean_last = self.last_name.rstrip(".")
            if len(clean_last) == 1 and clean_last.isalpha():
                self.is_last_initial = True
                self.last_initial_char = clean_last.upper()
            else:
                self.last_initial_char = clean_last[0].upper()

    @property
    def is_full_name(self) -> bool:
        """True if contains both non-initial first name and non-initial last name."""
        return (
            len(self.tokens) >= 2
            and not self.is_first_initial
            and not self.is_last_initial
        )

    @property
    def is_initial_and_surname(self) -> bool:
        """True if name format is 'R. Sharma' or 'R Sharma'."""
        return (
            len(self.tokens) == 2
            and self.is_first_initial
            and not self.is_last_initial
        )

    @property
    def is_title_and_surname(self) -> bool:
        """True if name format is 'Ms. Sharma' or 'Dr. Sharma'."""
        return (
            self.title is not None
            and len(self.tokens) == 1
            and len(self.tokens[0]) > 1
        )


class EntityResolver:
    """Multi-stage deterministic entity resolver with ambiguity safeguards."""

    @classmethod
    def resolve_entities(
        cls,
        document_id: str,
        candidates: List[Candidate],
        canonical_text: str = "",
        use_slm: bool = True,
    ) -> EntityGroupResponse:
        """Execute multi-stage entity resolution over candidates.
        
        Returns EntityGroupResponse with entity clusters, link evidence, and degraded mode status.
        """
        if not candidates:
            return EntityGroupResponse(
                document_id=document_id,
                total_entities=0,
                entities=[],
                degraded_mode=False,
                slm_available=False,
                warnings=[],
            )

        # Stage 1: Exact Normalized Matching
        clusters: Dict[str, Dict[str, Any]] = {}
        for cand in candidates:
            # Group key by category + normalized string
            norm_key = f"{cand.type}::{cand.text.strip().casefold()}"
            if norm_key not in clusters:
                clusters[norm_key] = {
                    "type": cand.type,
                    "canonical_name": cand.text.strip(),
                    "candidate_ids": [cand.candidate_id],
                    "variants": {cand.text.strip()},
                    "evidence": ["Exact normalized string match"],
                    "confidence": 1.0,
                    "is_ambiguous": False,
                }
            else:
                clusters[norm_key]["candidate_ids"].append(cand.candidate_id)
                clusters[norm_key]["variants"].add(cand.text.strip())
                # Update canonical name if this instance is longer/more detailed
                if len(cand.text.strip()) > len(clusters[norm_key]["canonical_name"]):
                    clusters[norm_key]["canonical_name"] = cand.text.strip()

        # Build initial entity list
        entities: List[Entity] = []
        ent_counter = 1
        for norm_key, data in clusters.items():
            ent = Entity(
                entity_id=f"ent_{ent_counter}",
                canonical_name=data["canonical_name"],
                entity_type=data["type"],
                candidate_ids=data["candidate_ids"],
                variants=sorted(list(data["variants"])),
                confidence=data["confidence"],
                evidence=data["evidence"],
                is_ambiguous=data["is_ambiguous"],
                is_user_defined=False,
            )
            entities.append(ent)
            ent_counter += 1

        # Multi-stage resolution for PERSON entities
        person_entities = [e for e in entities if e.entity_type == "PERSON"]
        non_person_entities = [e for e in entities if e.entity_type != "PERSON"]

        resolved_persons = cls._resolve_person_entities(person_entities)

        # Optional Stage 5: SLM Contextual Evidence Integration
        slm_available = False
        degraded_mode = False
        warnings: List[str] = []

        if use_slm and canonical_text:
            try:
                slm_available = ModelService.check_availability()
                if slm_available:
                    detected_names = [p.canonical_name for p in resolved_persons]
                    slm_resp = ModelService.analyze_context(canonical_text, detected_names)
                    if slm_resp and slm_resp.suggested_links:
                        cls._apply_slm_link_evidence(resolved_persons, slm_resp)
                else:
                    degraded_mode = True
                    warnings.append("Local SLM is offline. Entity resolution operated in rule-based degraded mode.")
            except Exception as exc:
                degraded_mode = True
                warnings.append(f"SLM analysis failed: {str(exc)}. Fallback rule-based resolution applied.")

        # Recombine entities and re-index entity_ids cleanly
        all_entities = resolved_persons + non_person_entities
        final_entities: List[Entity] = []
        for idx, ent in enumerate(all_entities, start=1):
            ent.entity_id = f"ent_{idx}"
            final_entities.append(ent)

        # Save to session storage and update candidates
        cls._persist_resolution(document_id, final_entities, candidates)

        return EntityGroupResponse(
            document_id=document_id,
            total_entities=len(final_entities),
            entities=final_entities,
            degraded_mode=degraded_mode,
            slm_available=slm_available,
            warnings=warnings,
        )

    @classmethod
    def _resolve_person_entities(cls, person_entities: List[Entity]) -> List[Entity]:
        """Perform conservative initial, title, and fuzzy linkage across PERSON entities."""
        if len(person_entities) <= 1:
            return person_entities

        # Identify full-name anchors (e.g. "Richa Sharma", "John Smith")
        anchors: List[Tuple[Entity, NameComponents]] = []
        for ent in person_entities:
            parsed = NameComponents(ent.canonical_name)
            if parsed.is_full_name:
                anchors.append((ent, parsed))

        merged_into: Dict[str, str] = {}  # source_id -> target_id
        link_evidence: Dict[str, List[str]] = {}

        # Stage 2: Initial-to-Full Name Matching with Ambiguity Safeguard
        for ent in person_entities:
            if ent.entity_id in merged_into:
                continue

            parsed = NameComponents(ent.canonical_name)
            if parsed.is_initial_and_surname:
                surname = parsed.last_name.casefold() if parsed.last_name else ""
                init = parsed.first_initial_char

                # Find all matching full-name anchors with same surname and same initial
                matching_anchors = [
                    (a_ent, a_p) for (a_ent, a_p) in anchors
                    if a_p.last_name and a_p.last_name.casefold() == surname
                    and a_p.first_initial_char == init
                    and a_ent.entity_id != ent.entity_id
                ]

                if len(matching_anchors) == 1:
                    # Exactly one matching person: SAFE TO LINK
                    target_ent, target_parsed = matching_anchors[0]
                    merged_into[ent.entity_id] = target_ent.entity_id
                    evidence_str = (
                        f"Unambiguous initial match: '{ent.canonical_name}' linked to "
                        f"'{target_ent.canonical_name}' (shared surname '{parsed.last_name}', initial '{init}')"
                    )
                    link_evidence.setdefault(target_ent.entity_id, []).append(evidence_str)
                elif len(matching_anchors) > 1:
                    # Ambiguous initials: DO NOT MERGE
                    ent.is_ambiguous = True
                    match_names = [a[0].canonical_name for a in matching_anchors]
                    ent.evidence.append(
                        f"Ambiguous initial: '{ent.canonical_name}' matches multiple distinct candidates: {match_names}. Kept separate."
                    )

            elif parsed.is_title_and_surname:
                # Stage 3: Title + Surname matching (e.g. "Ms. Sharma")
                surname = parsed.tokens[0].casefold() if parsed.tokens else ""
                matching_anchors = [
                    (a_ent, a_p) for (a_ent, a_p) in anchors
                    if a_p.last_name and a_p.last_name.casefold() == surname
                    and a_ent.entity_id != ent.entity_id
                ]

                if len(matching_anchors) == 1:
                    target_ent, target_parsed = matching_anchors[0]
                    merged_into[ent.entity_id] = target_ent.entity_id
                    evidence_str = (
                        f"Title-variant match: '{ent.canonical_name}' linked to "
                        f"'{target_ent.canonical_name}' (shared surname '{parsed.tokens[0]}')"
                    )
                    link_evidence.setdefault(target_ent.entity_id, []).append(evidence_str)
                elif len(matching_anchors) > 1:
                    ent.is_ambiguous = True
                    match_names = [a[0].canonical_name for a in matching_anchors]
                    ent.evidence.append(
                        f"Ambiguous title: '{ent.canonical_name}' matches multiple distinct candidates: {match_names}. Kept separate."
                    )

        # Stage 4: RapidFuzz Lexical Similarity Proposals (for minor typos like Swastik vs Swasthik)
        active_entities = [e for e in person_entities if e.entity_id not in merged_into]
        for i in range(len(active_entities)):
            ent_a = active_entities[i]
            if ent_a.entity_id in merged_into:
                continue
            parsed_a = NameComponents(ent_a.canonical_name)

            for j in range(i + 1, len(active_entities)):
                ent_b = active_entities[j]
                if ent_b.entity_id in merged_into:
                    continue
                parsed_b = NameComponents(ent_b.canonical_name)

                # DO NOT merge if distinct full first names with different initials (e.g. Anil Kumar vs Sunil Kumar)
                if (
                    parsed_a.first_initial_char and parsed_b.first_initial_char
                    and parsed_a.first_initial_char != parsed_b.first_initial_char
                ):
                    continue

                sim = fuzz.token_sort_ratio(ent_a.canonical_name, ent_b.canonical_name)
                if sim >= 88:
                    # Minor lexical typo/transposition: merge into longer/richer representation
                    target = ent_a if len(ent_a.canonical_name) >= len(ent_b.canonical_name) else ent_b
                    source = ent_b if target == ent_a else ent_a

                    merged_into[source.entity_id] = target.entity_id
                    evidence_str = f"Fuzzy lexical similarity ({sim:.1f}%): linked '{source.canonical_name}' to '{target.canonical_name}'"
                    link_evidence.setdefault(target.entity_id, []).append(evidence_str)

        # Perform actual cluster merging
        surviving_entities: Dict[str, Entity] = {}
        for ent in person_entities:
            # Follow merge chain
            curr_id = ent.entity_id
            while curr_id in merged_into:
                curr_id = merged_into[curr_id]

            if curr_id not in surviving_entities:
                surviving_entities[curr_id] = ent
            else:
                target = surviving_entities[curr_id]
                if target.entity_id != ent.entity_id:
                    target.candidate_ids.extend(ent.candidate_ids)
                    target.variants = sorted(list(set(target.variants + ent.variants)))
                    if ent.is_ambiguous:
                        target.is_ambiguous = True

        # Attach accumulated evidence
        for ent_id, target in surviving_entities.items():
            if ent_id in link_evidence:
                target.evidence.extend(link_evidence[ent_id])
                # Adjust confidence if linked via heuristic
                target.confidence = min(target.confidence, 0.85)

        return list(surviving_entities.values())

    @classmethod
    def _apply_slm_link_evidence(
        cls,
        person_entities: List[Entity],
        slm_resp: SLMAnalysisResponse,
    ) -> None:
        """Incorporate SLM suggestions as supporting evidence without bypassing rules."""
        for link in slm_resp.suggested_links:
            source_lower = link.source_text.strip().casefold()
            target_lower = link.target_text.strip().casefold()

            for ent in person_entities:
                variants_lower = [v.casefold() for v in ent.variants]
                if source_lower in variants_lower or target_lower in variants_lower:
                    ent.evidence.append(
                        f"SLM supporting evidence: {link.relation_type} ({link.reason}, confidence={link.confidence:.2f})"
                    )

    @classmethod
    def link_candidates(
        cls,
        document_id: str,
        candidate_ids: List[str],
        target_entity_id: Optional[str] = None,
    ) -> EntityGroupResponse:
        """Manually link candidates into a designated or newly created entity cluster."""
        session_dir = get_safe_session_dir(document_id)
        entities = cls.load_entities(document_id)
        candidates = cls.load_candidates(document_id)

        target_entity: Optional[Entity] = None
        if target_entity_id:
            target_entity = next((e for e in entities if e.entity_id == target_entity_id), None)

        # Collect candidate texts
        cands_map = {c.candidate_id: c for c in candidates}
        selected_cands = [cands_map[cid] for cid in candidate_ids if cid in cands_map]

        if not selected_cands:
            raise ValueError(f"None of the candidate IDs {candidate_ids} found in document session.")

        # Remove candidate_ids from any existing entities
        for ent in entities:
            ent.candidate_ids = [cid for cid in ent.candidate_ids if cid not in candidate_ids]

        if target_entity:
            target_entity.candidate_ids.extend(candidate_ids)
            for c in selected_cands:
                if c.text not in target_entity.variants:
                    target_entity.variants.append(c.text)
            target_entity.evidence.append("User manual linkage")
            target_entity.is_user_defined = True
        else:
            # Create new entity cluster
            new_id = f"ent_{len(entities) + 1}"
            longest_name = max((c.text for c in selected_cands), key=len)
            target_entity = Entity(
                entity_id=new_id,
                canonical_name=longest_name,
                entity_type=selected_cands[0].type,
                candidate_ids=candidate_ids,
                variants=sorted(list(set(c.text for c in selected_cands))),
                confidence=1.0,
                evidence=["User manual entity creation"],
                is_ambiguous=False,
                is_user_defined=True,
            )
            entities.append(target_entity)

        # Clean up any empty entities
        entities = [e for e in entities if len(e.candidate_ids) > 0]

        cls._persist_resolution(document_id, entities, candidates)

        # Record data-minimized entity action feedback
        try:
            FeedbackService.record_entity_action_feedback(
                document_id=document_id,
                action=FeedbackAction.LINK_ENTITIES if target_entity_id else FeedbackAction.MERGE_ENTITIES,
                entity_id=target_entity.entity_id if target_entity else None,
                entity_type=target_entity.entity_type if target_entity else "UNKNOWN",
                affected_count=len(candidate_ids),
                details_meta={"target_entity_id": target_entity_id, "is_new_cluster": target_entity_id is None},
            )
        except Exception as e:
            logger.warning("Failed to record entity feedback: %s", e)

        return EntityGroupResponse(
            document_id=document_id,
            total_entities=len(entities),
            entities=entities,
            degraded_mode=False,
            slm_available=True,
            warnings=[],
        )

    @classmethod
    def unlink_candidates(
        cls,
        document_id: str,
        candidate_ids: List[str],
    ) -> EntityGroupResponse:
        """Manually unlink candidates from their current entity, splitting them into isolated clusters."""
        entities = cls.load_entities(document_id)
        candidates = cls.load_candidates(document_id)
        cands_map = {c.candidate_id: c for c in candidates}

        for cid in candidate_ids:
            # Remove from existing entity
            for ent in entities:
                if cid in ent.candidate_ids:
                    ent.candidate_ids.remove(cid)
                    ent.is_user_defined = True
                    ent.evidence.append(f"Candidate {cid} manually unlinked by user")

            # Create an independent single-candidate entity
            if cid in cands_map:
                cand = cands_map[cid]
                new_ent = Entity(
                    entity_id=f"ent_{len(entities) + 1}",
                    canonical_name=cand.text,
                    entity_type=cand.type,
                    candidate_ids=[cid],
                    variants=[cand.text],
                    confidence=1.0,
                    evidence=["Manually unlinked by user into standalone entity"],
                    is_ambiguous=False,
                    is_user_defined=True,
                )
                entities.append(new_ent)

        entities = [e for e in entities if len(e.candidate_ids) > 0]
        cls._persist_resolution(document_id, entities, candidates)

        # Record data-minimized entity action feedback
        try:
            FeedbackService.record_entity_action_feedback(
                document_id=document_id,
                action=FeedbackAction.UNLINK_ENTITIES,
                entity_id=None,
                entity_type="PERSON",
                affected_count=len(candidate_ids),
                details_meta={"unlinked_candidate_ids_count": len(candidate_ids)},
            )
        except Exception as e:
            logger.warning("Failed to record entity unlink feedback: %s", e)

        return EntityGroupResponse(
            document_id=document_id,
            total_entities=len(entities),
            entities=entities,
            degraded_mode=False,
            slm_available=True,
            warnings=[],
        )

    # =========================================================================
    # Session Persistence Utilities
    # =========================================================================

    @classmethod
    def _persist_resolution(
        cls,
        document_id: str,
        entities: List[Entity],
        candidates: List[Candidate],
    ) -> None:
        """Store resolved entities and update candidate entity_id references in session dir."""
        session_dir = get_safe_session_dir(document_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        # Map candidate_id -> entity_id
        cand_to_ent: Dict[str, str] = {}
        for ent in entities:
            for cid in ent.candidate_ids:
                cand_to_ent[cid] = ent.entity_id

        for cand in candidates:
            cand.entity_id = cand_to_ent.get(cand.candidate_id)

        # Write entities.json
        entities_path = session_dir / "entities.json"
        ent_data = [e.model_dump() for e in entities]
        entities_path.write_text(json.dumps(ent_data, indent=2), encoding="utf-8")

        # Write updated candidates.json
        cands_path = session_dir / "candidates.json"
        cands_data = [c.model_dump() for c in candidates]
        cands_path.write_text(json.dumps(cands_data, indent=2), encoding="utf-8")

    @classmethod
    def save_entities(cls, document_id: str, entities: List[Entity]) -> None:
        """Save resolved entity clusters to session storage."""
        session_dir = get_safe_session_dir(document_id)
        entities_path = session_dir / "entities.json"
        ent_data = [e.model_dump() for e in entities]
        entities_path.write_text(json.dumps(ent_data, indent=2), encoding="utf-8")

    @classmethod
    def load_entities(cls, document_id: str) -> List[Entity]:
        """Load resolved entity clusters from session storage."""
        session_dir = get_safe_session_dir(document_id)
        entities_path = session_dir / "entities.json"
        if not entities_path.exists():
            return []
        raw = json.loads(entities_path.read_text(encoding="utf-8"))
        return [Entity(**item) for item in raw]

    @classmethod
    def save_candidates(cls, document_id: str, candidates: List[Candidate]) -> None:
        """Save candidates to session storage."""
        session_dir = get_safe_session_dir(document_id)
        cands_path = session_dir / "candidates.json"
        cands_data = [c.model_dump() for c in candidates]
        cands_path.write_text(json.dumps(cands_data, indent=2), encoding="utf-8")

    @classmethod
    def load_candidates(cls, document_id: str) -> List[Candidate]:
        """Load candidates from session storage."""
        session_dir = get_safe_session_dir(document_id)
        cands_path = session_dir / "candidates.json"
        if not cands_path.exists():
            return []
        raw = json.loads(cands_path.read_text(encoding="utf-8"))
        return [Candidate(**item) for item in raw]
