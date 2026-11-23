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
from typing import Any, Dict, List, Optional, Set, Tuple
from rapidfuzz import fuzz

from app.core.security import atomic_write_text, get_safe_session_dir
from app.database.session import record_review_decision
from app.schemas.candidate import Candidate
from app.schemas.entity import (
    Entity,
    EntityGroupResponse,
    EntityLinkAction,
    EntityLinkReason,
    ResolutionTier,
    SLMAnalysisResponse,
)
from app.schemas.feedback import FeedbackAction
from app.services.feedback_service import FeedbackService
from app.services.model_service import ModelService

logger = logging.getLogger(__name__)

TITLES: Set[str] = {
    "dr", "dr.", "mr", "mr.", "ms", "ms.", "mrs", "mrs.",
    "prof", "prof.", "shri", "smt", "rev", "rev."
}


def _phonetic_key(token: str) -> str:
    """Compute a deterministic phonetic key for English and Indian transliterated names.

    Normalizes aspirated consonants (bh->b, dh->d, gh->g, kh->k, ph->f, th->t, sh->s, ch->c),
    vowel diphthongs (aa->a, ee/ii->i, oo/ou/ow->u, ai/ay->e), and collapses duplicate letters.
    """
    s = re.sub(r"[^a-z]", "", token.strip().casefold())
    if not s:
        return ""
    for src, dst in (
        ("ph", "f"),
        ("th", "t"),
        ("sh", "s"),
        ("ch", "c"),
        ("bh", "b"),
        ("dh", "d"),
        ("gh", "g"),
        ("jh", "j"),
        ("kh", "k"),
        ("ck", "k"),
        ("qu", "k"),
        ("w", "v"),
        ("y", "i"),
        ("aa", "a"),
        ("ee", "i"),
        ("ii", "i"),
        ("oo", "u"),
        ("ou", "u"),
        ("ow", "u"),
        ("au", "u"),
        ("ai", "e"),
        ("ei", "i"),
    ):
        s = s.replace(src, dst)
    # Collapse consecutive identical characters
    collapsed = [s[0]]
    for ch in s[1:]:
        if ch != collapsed[-1]:
            collapsed.append(ch)
    return "".join(collapsed)


def parse_phone_country_and_subscriber(raw_text: str) -> Tuple[Optional[str], str]:
    """Parse a phone string into (explicit_country_code, national_subscriber_digits).

    Safeguard:
    - Preserves explicit international prefixes (+91, +1, +44, etc.).
    - Strips domestic trunk prefix '0' on 11-digit numbers.
    - Never guesses or invents a country code when none is present.
    """
    s = raw_text.strip()
    has_plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    if has_plus:
        if digits.startswith("91") and len(digits) == 12:
            return "+91", digits[2:]
        if digits.startswith("1") and len(digits) == 11:
            return "+1", digits[1:]
        if digits.startswith("44") and len(digits) in (11, 12):
            return "+44", digits[2:]
        if len(digits) > 10:
            cc_len = len(digits) - 10
            return f"+{digits[:cc_len]}", digits[cc_len:]
        return f"+{digits[:2]}", digits[2:]
    else:
        if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
            return "+91", digits[2:]
        if len(digits) == 11 and digits.startswith("0"):
            return None, digits[1:]
        return None, digits


def normalize_by_category(cand_type: str, raw_text: str) -> str:
    """Compute a category-aware normalized key for Stage 1 clustering."""
    s = raw_text.strip()
    cat = (cand_type or "").upper()

    if cat == "EMAIL":
        # Normalize obfuscated email forms: user [at] domain [dot] com -> user@domain.com
        norm = re.sub(r"\s*(?:\[\s*at\s*\]|\(\s*at\s*\)|\bat\b)\s*", "@", s, flags=re.IGNORECASE)
        norm = re.sub(r"\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\bdot\b)\s*", ".", norm, flags=re.IGNORECASE)
        return norm.strip().casefold()

    if cat == "PHONE":
        cc, sub = parse_phone_country_and_subscriber(s)
        if cc:
            return f"{cc}-{sub}"
        return f"nat-{sub}"

    if cat == "ID_LIKE":
        # Collapse spaces/underscores/hyphens for same-format IDs while preserving masked X's
        return re.sub(r"[\s_-]+", "-", s.upper())

    if cat == "ADDRESS":
        norm = re.sub(r"\s+", " ", s.casefold()).rstrip(".,;")
        norm = re.sub(r"\bst\.?(?=\s|,|$)", "street", norm)
        norm = re.sub(r"\brd\.?(?=\s|,|$)", "road", norm)
        norm = re.sub(r"\bave\.?(?=\s|,|$)", "avenue", norm)
        norm = re.sub(r"\bblvd\.?(?=\s|,|$)", "boulevard", norm)
        norm = re.sub(r"\bbangalore\b", "bengaluru", norm)
        norm = re.sub(r"\bgurgaon\b", "gurugram", norm)
        norm = re.sub(r"\s*-\s*(?=\d{6}\b)", " ", norm)
        return norm

    # Default / PERSON: whitespace-normalized casefold
    return re.sub(r"\s+", " ", s).casefold()


class NameComponents:
    """Helper to parse and extract person name components, initials, and phonetic keys."""

    def __init__(self, raw_text: str):
        self.raw = raw_text.strip()
        # Expand compact initials like "R.K. Sharma" -> ["R.", "K.", "Sharma"]
        expanded = re.sub(r"\b([A-Za-z])\.([A-Za-z])\.", r"\1. \2.", self.raw)
        tokens = [t for t in expanded.split() if t]

        self.title: Optional[str] = None
        if tokens and tokens[0].lower() in TITLES:
            self.title = tokens[0]
            tokens = tokens[1:]

        self.tokens = tokens
        self.first_name: Optional[str] = tokens[0] if len(tokens) >= 1 else None
        self.last_name: Optional[str] = tokens[-1] if len(tokens) >= 2 else None

        # Check initial representations across all leading tokens before surname
        self.leading_initials: List[str] = []
        if len(tokens) >= 2:
            for tok in tokens[:-1]:
                clean_tok = tok.rstrip(".")
                if len(clean_tok) == 1 and clean_tok.isalpha():
                    self.leading_initials.append(clean_tok.upper())
                else:
                    break

        self.is_first_initial: bool = False
        self.first_initial_char: Optional[str] = None
        if self.first_name:
            clean_first = self.first_name.rstrip(".")
            if len(clean_first) == 1 and clean_first.isalpha():
                self.is_first_initial = True
                self.first_initial_char = clean_first.upper()
            elif clean_first:
                self.first_initial_char = clean_first[0].upper()

        self.is_last_initial: bool = False
        self.last_initial_char: Optional[str] = None
        if self.last_name:
            clean_last = self.last_name.rstrip(".")
            if len(clean_last) == 1 and clean_last.isalpha():
                self.is_last_initial = True
                self.last_initial_char = clean_last.upper()
            elif clean_last:
                self.last_initial_char = clean_last[0].upper()

    @property
    def token_initials(self) -> List[str]:
        """Sequence of uppercase first letters for all tokens before the surname."""
        if len(self.tokens) < 2:
            return []
        result = []
        for tok in self.tokens[:-1]:
            c = tok.rstrip(".")
            if c and c[0].isalpha():
                result.append(c[0].upper())
        return result

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
    def is_multi_initial_and_surname(self) -> bool:
        """True if name format is 'R. K. Sharma' or 'J. R. R. Tolkien'."""
        return (
            len(self.tokens) >= 3
            and len(self.leading_initials) == len(self.tokens) - 1
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

    @property
    def is_standalone_surname(self) -> bool:
        """True if single-token surname reference without title (e.g. 'Vance', 'Sharma')."""
        return (
            self.title is None
            and len(self.tokens) == 1
            and len(self.tokens[0].rstrip(".")) >= 3
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

        # Stage 1: Category-Aware Exact & Normalized Matching
        clusters: Dict[str, Dict[str, Any]] = {}
        for cand in candidates:
            norm_val = normalize_by_category(cand.type, cand.text)
            norm_key = f"{cand.type}::{norm_val}"
            surface = cand.text.strip()
            if norm_key not in clusters:
                clusters[norm_key] = {
                    "type": cand.type,
                    "canonical_name": surface,
                    "normalized_value": norm_val,
                    "candidate_ids": [cand.candidate_id],
                    "variants": {surface},
                    "evidence": ["Exact normalized string match"],
                    "link_reasons": [
                        EntityLinkReason(
                            rule="EXACT_NORMALIZED",
                            source_variant=surface,
                            target_variant=surface,
                            score=1.0,
                            explanation=f"Category-normalized {cand.type} match ('{norm_val}')",
                        )
                    ],
                    "confidence": 1.0,
                    "is_ambiguous": False,
                }
            else:
                clusters[norm_key]["candidate_ids"].append(cand.candidate_id)
                if surface not in clusters[norm_key]["variants"]:
                    clusters[norm_key]["variants"].add(surface)
                    rule_name = (
                        "OBFUSCATED_EMAIL_NORMALIZATION"
                        if cand.type == "EMAIL" and "@" not in surface
                        else "CATEGORY_NORMALIZED_MATCH"
                    )
                    clusters[norm_key]["link_reasons"].append(
                        EntityLinkReason(
                            rule=rule_name,
                            source_variant=surface,
                            target_variant=clusters[norm_key]["canonical_name"],
                            score=0.98,
                            explanation=f"Normalized {cand.type} variant '{surface}' matched '{clusters[norm_key]['canonical_name']}'",
                        )
                    )
                # Prefer non-obfuscated / longer canonical representation
                if cand.type == "EMAIL" and "@" in surface and "@" not in clusters[norm_key]["canonical_name"]:
                    clusters[norm_key]["canonical_name"] = surface
                elif len(surface) > len(clusters[norm_key]["canonical_name"]) and cand.type != "EMAIL":
                    clusters[norm_key]["canonical_name"] = surface

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
                resolution_tier=ResolutionTier.EXACT.value,
                evidence=data["evidence"],
                link_reasons=data["link_reasons"],
                normalized_value=data["normalized_value"],
                is_ambiguous=data["is_ambiguous"],
                is_user_defined=False,
            )
            entities.append(ent)
            ent_counter += 1

        # Multi-stage resolution for PERSON and PHONE entities
        person_entities = [e for e in entities if e.entity_type == "PERSON"]
        phone_entities = [e for e in entities if e.entity_type == "PHONE"]
        other_entities = [e for e in entities if e.entity_type not in ("PERSON", "PHONE")]

        resolved_persons = cls._resolve_person_entities(person_entities)
        resolved_phones = cls._resolve_phone_entities(phone_entities)
        non_person_entities = resolved_phones + other_entities

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
    def _resolve_phone_entities(cls, phone_entities: List[Entity]) -> List[Entity]:
        """Link national 10-digit phone numbers to unambiguous country-prefixed numbers in the same document.

        Safeguard: Never merge phone numbers with different explicit country codes (e.g. +1 vs +91).
        """
        if len(phone_entities) <= 1:
            return phone_entities

        intl_anchors: List[Tuple[Entity, str, str]] = []
        for ent in phone_entities:
            cc, sub = parse_phone_country_and_subscriber(ent.canonical_name)
            if cc is not None and len(sub) >= 10:
                intl_anchors.append((ent, cc, sub))

        merged_into: Dict[str, str] = {}
        for ent in phone_entities:
            cc, sub = parse_phone_country_and_subscriber(ent.canonical_name)
            if cc is None and len(sub) >= 10:
                matching_intl = [
                    (a_ent, a_cc, a_sub)
                    for (a_ent, a_cc, a_sub) in intl_anchors
                    if a_sub == sub and a_ent.entity_id != ent.entity_id
                ]
                distinct_ccs = {a_cc for (_, a_cc, _) in matching_intl}
                if len(matching_intl) == 1 and len(distinct_ccs) == 1:
                    target_ent, target_cc, _ = matching_intl[0]
                    merged_into[ent.entity_id] = target_ent.entity_id
                    ev = (
                        f"Country-aware phone match: national number '{ent.canonical_name}' "
                        f"linked to '{target_ent.canonical_name}' ({target_cc})"
                    )
                    target_ent.evidence.append(ev)
                    target_ent.link_reasons.append(
                        EntityLinkReason(
                            rule="COUNTRY_AWARE_PHONE",
                            source_variant=ent.canonical_name,
                            target_variant=target_ent.canonical_name,
                            score=0.94,
                            explanation=ev,
                        )
                    )
                    target_ent.resolution_tier = ResolutionTier.DETERMINISTIC_VARIANT.value
                    target_ent.confidence = min(target_ent.confidence, 0.94)
                elif len(distinct_ccs) > 1:
                    ent.is_ambiguous = True
                    ent.resolution_tier = ResolutionTier.AMBIGUOUS_CONFLICT.value
                    ev = (
                        f"Ambiguous national phone '{ent.canonical_name}' matches multiple country codes "
                        f"({sorted(list(distinct_ccs))}). Kept separate."
                    )
                    ent.evidence.append(ev)
                    ent.link_reasons.append(
                        EntityLinkReason(
                            rule="AMBIGUITY_SAFEGUARD",
                            source_variant=ent.canonical_name,
                            target_variant=", ".join(a[0].canonical_name for a in matching_intl),
                            score=0.50,
                            explanation=ev,
                        )
                    )

        entity_by_id = {e.entity_id: e for e in phone_entities}
        surviving: Dict[str, Entity] = {}
        for ent in phone_entities:
            curr = ent.entity_id
            visited: Set[str] = set()
            while curr in merged_into and curr not in visited:
                visited.add(curr)
                curr = merged_into[curr]
            if curr not in surviving:
                surviving[curr] = entity_by_id[curr]
            if ent.entity_id != curr:
                target = surviving[curr]
                target.candidate_ids.extend(ent.candidate_ids)
                target.variants = sorted(list(set(target.variants + ent.variants)))

        return list(surviving.values())

    @classmethod
    def _resolve_person_entities(cls, person_entities: List[Entity]) -> List[Entity]:
        """Perform conservative initial, multi-initial, title, standalone surname, and phonetic/fuzzy linkage."""
        if len(person_entities) <= 1:
            return person_entities

        # Pre-pass: Merge exact full-name token matches after honorific stripping (e.g. "Dr. Richa Sharma" == "Richa Sharma")
        merged_into: Dict[str, str] = {}
        link_evidence: Dict[str, List[str]] = {}
        link_reasons_map: Dict[str, List[EntityLinkReason]] = {}
        tier_map: Dict[str, str] = {}

        for i in range(len(person_entities)):
            ent_a = person_entities[i]
            if ent_a.entity_id in merged_into:
                continue
            parsed_a = NameComponents(ent_a.canonical_name)
            if not parsed_a.is_full_name:
                continue
            for j in range(i + 1, len(person_entities)):
                ent_b = person_entities[j]
                if ent_b.entity_id in merged_into:
                    continue
                parsed_b = NameComponents(ent_b.canonical_name)
                if (
                    parsed_b.is_full_name
                    and [t.casefold() for t in parsed_a.tokens] == [t.casefold() for t in parsed_b.tokens]
                ):
                    # Prefer the non-titled full name as canonical_name (or longer if neither/both titled)
                    target = ent_b if (parsed_a.title and not parsed_b.title) else ent_a
                    source = ent_a if target == ent_b else ent_b
                    merged_into[source.entity_id] = target.entity_id
                    ev = f"Honorific full-name match: linked '{source.canonical_name}' to '{target.canonical_name}'"
                    link_evidence.setdefault(target.entity_id, []).append(ev)
                    link_reasons_map.setdefault(target.entity_id, []).append(
                        EntityLinkReason(
                            rule="HONORIFIC_FULL_NAME",
                            source_variant=source.canonical_name,
                            target_variant=target.canonical_name,
                            score=0.96,
                            explanation=ev,
                        )
                    )
                    tier_map[target.entity_id] = ResolutionTier.DETERMINISTIC_VARIANT.value

        # Identify distinct active full-name anchors (e.g. "Richa Sharma", "John Smith")
        anchors: List[Tuple[Entity, NameComponents]] = []
        for ent in person_entities:
            if ent.entity_id in merged_into:
                continue
            parsed = NameComponents(ent.canonical_name)
            if parsed.is_full_name:
                anchors.append((ent, parsed))

        # Stage 2 & 3: Initial, Multi-Initial, Title+Surname, and Standalone Surname Matching
        for ent in person_entities:
            if ent.entity_id in merged_into:
                continue

            parsed = NameComponents(ent.canonical_name)

            # 2a. Single Initial + Surname (e.g. "R. Sharma")
            if parsed.is_initial_and_surname:
                surname = parsed.last_name.casefold() if parsed.last_name else ""
                init = parsed.first_initial_char

                matching_anchors = [
                    (a_ent, a_p) for (a_ent, a_p) in anchors
                    if a_p.last_name and a_p.last_name.casefold() == surname
                    and a_p.first_initial_char == init
                    and a_ent.entity_id != ent.entity_id
                ]

                if len(matching_anchors) == 1:
                    target_ent, _ = matching_anchors[0]
                    merged_into[ent.entity_id] = target_ent.entity_id
                    evidence_str = (
                        f"Unambiguous initial match: '{ent.canonical_name}' linked to "
                        f"'{target_ent.canonical_name}' (shared surname '{parsed.last_name}', initial '{init}')"
                    )
                    link_evidence.setdefault(target_ent.entity_id, []).append(evidence_str)
                    link_reasons_map.setdefault(target_ent.entity_id, []).append(
                        EntityLinkReason(
                            rule="UNAMBIGUOUS_INITIAL",
                            source_variant=ent.canonical_name,
                            target_variant=target_ent.canonical_name,
                            score=0.90,
                            explanation=evidence_str,
                        )
                    )
                    tier_map.setdefault(target_ent.entity_id, ResolutionTier.DETERMINISTIC_VARIANT.value)
                elif len(matching_anchors) > 1:
                    ent.is_ambiguous = True
                    ent.resolution_tier = ResolutionTier.AMBIGUOUS_CONFLICT.value
                    match_names = [a[0].canonical_name for a in matching_anchors]
                    ev = f"Ambiguous initial: '{ent.canonical_name}' matches multiple distinct candidates: {match_names}. Kept separate."
                    ent.evidence.append(ev)
                    ent.link_reasons.append(
                        EntityLinkReason(
                            rule="AMBIGUITY_SAFEGUARD",
                            source_variant=ent.canonical_name,
                            target_variant=", ".join(match_names),
                            score=0.45,
                            explanation=ev,
                        )
                    )

            # 2b. Multi-Initial + Surname (e.g. "R. K. Sharma" -> "Richa K. Sharma" or "Richa Sharma")
            elif parsed.is_multi_initial_and_surname:
                surname = parsed.last_name.casefold() if parsed.last_name else ""
                inits = parsed.leading_initials

                # Prefer exact initial-sequence match, fallback to first-initial match if unique
                exact_init_anchors = [
                    (a_ent, a_p) for (a_ent, a_p) in anchors
                    if a_p.last_name and a_p.last_name.casefold() == surname
                    and a_p.token_initials == inits
                    and a_ent.entity_id != ent.entity_id
                ]
                first_init_anchors = [
                    (a_ent, a_p) for (a_ent, a_p) in anchors
                    if a_p.last_name and a_p.last_name.casefold() == surname
                    and a_p.first_initial_char == inits[0]
                    and (len(a_p.token_initials) == 1 or a_p.token_initials == inits)
                    and a_ent.entity_id != ent.entity_id
                ]
                matching_anchors = exact_init_anchors if exact_init_anchors else first_init_anchors

                if len(matching_anchors) == 1:
                    target_ent, _ = matching_anchors[0]
                    merged_into[ent.entity_id] = target_ent.entity_id
                    evidence_str = (
                        f"Multi-initial match: '{ent.canonical_name}' linked to "
                        f"'{target_ent.canonical_name}' (initials {'.'.join(inits)}., surname '{parsed.last_name}')"
                    )
                    link_evidence.setdefault(target_ent.entity_id, []).append(evidence_str)
                    link_reasons_map.setdefault(target_ent.entity_id, []).append(
                        EntityLinkReason(
                            rule="MULTI_INITIAL_SURNAME",
                            source_variant=ent.canonical_name,
                            target_variant=target_ent.canonical_name,
                            score=0.91,
                            explanation=evidence_str,
                        )
                    )
                    tier_map.setdefault(target_ent.entity_id, ResolutionTier.DETERMINISTIC_VARIANT.value)
                elif len(matching_anchors) > 1:
                    ent.is_ambiguous = True
                    ent.resolution_tier = ResolutionTier.AMBIGUOUS_CONFLICT.value
                    match_names = [a[0].canonical_name for a in matching_anchors]
                    ev = f"Ambiguous multi-initial: '{ent.canonical_name}' matches multiple distinct candidates: {match_names}. Kept separate."
                    ent.evidence.append(ev)
                    ent.link_reasons.append(
                        EntityLinkReason(
                            rule="AMBIGUITY_SAFEGUARD",
                            source_variant=ent.canonical_name,
                            target_variant=", ".join(match_names),
                            score=0.45,
                            explanation=ev,
                        )
                    )

            # 3a. Title + Surname matching (e.g. "Ms. Sharma")
            elif parsed.is_title_and_surname:
                surname = parsed.tokens[0].casefold() if parsed.tokens else ""
                matching_anchors = [
                    (a_ent, a_p) for (a_ent, a_p) in anchors
                    if a_p.last_name and a_p.last_name.casefold() == surname
                    and a_ent.entity_id != ent.entity_id
                ]

                if len(matching_anchors) == 1:
                    target_ent, _ = matching_anchors[0]
                    merged_into[ent.entity_id] = target_ent.entity_id
                    evidence_str = (
                        f"Title-variant match: '{ent.canonical_name}' linked to "
                        f"'{target_ent.canonical_name}' (shared surname '{parsed.tokens[0]}')"
                    )
                    link_evidence.setdefault(target_ent.entity_id, []).append(evidence_str)
                    link_reasons_map.setdefault(target_ent.entity_id, []).append(
                        EntityLinkReason(
                            rule="TITLE_SURNAME",
                            source_variant=ent.canonical_name,
                            target_variant=target_ent.canonical_name,
                            score=0.88,
                            explanation=evidence_str,
                        )
                    )
                    tier_map.setdefault(target_ent.entity_id, ResolutionTier.DETERMINISTIC_VARIANT.value)
                elif len(matching_anchors) > 1:
                    ent.is_ambiguous = True
                    ent.resolution_tier = ResolutionTier.AMBIGUOUS_CONFLICT.value
                    match_names = [a[0].canonical_name for a in matching_anchors]
                    ev = f"Ambiguous title: '{ent.canonical_name}' matches multiple distinct candidates: {match_names}. Kept separate."
                    ent.evidence.append(ev)
                    ent.link_reasons.append(
                        EntityLinkReason(
                            rule="AMBIGUITY_SAFEGUARD",
                            source_variant=ent.canonical_name,
                            target_variant=", ".join(match_names),
                            score=0.45,
                            explanation=ev,
                        )
                    )

            # 3b. Standalone Document-Local Surname Coreference (e.g. "Vance" -> "Elena Vance")
            elif parsed.is_standalone_surname:
                surname = parsed.tokens[0].casefold()
                matching_anchors = [
                    (a_ent, a_p) for (a_ent, a_p) in anchors
                    if a_p.last_name and a_p.last_name.casefold() == surname
                    and a_ent.entity_id != ent.entity_id
                ]
                if len(matching_anchors) == 1:
                    target_ent, _ = matching_anchors[0]
                    merged_into[ent.entity_id] = target_ent.entity_id
                    evidence_str = (
                        f"Document-local surname coreference: standalone '{ent.canonical_name}' linked to "
                        f"unique anchor '{target_ent.canonical_name}'"
                    )
                    link_evidence.setdefault(target_ent.entity_id, []).append(evidence_str)
                    link_reasons_map.setdefault(target_ent.entity_id, []).append(
                        EntityLinkReason(
                            rule="DOCUMENT_LOCAL_SURNAME",
                            source_variant=ent.canonical_name,
                            target_variant=target_ent.canonical_name,
                            score=0.84,
                            explanation=evidence_str,
                        )
                    )
                    tier_map.setdefault(target_ent.entity_id, ResolutionTier.DETERMINISTIC_VARIANT.value)
                elif len(matching_anchors) > 1:
                    ent.is_ambiguous = True
                    ent.resolution_tier = ResolutionTier.AMBIGUOUS_CONFLICT.value
                    match_names = [a[0].canonical_name for a in matching_anchors]
                    ev = (
                        f"Ambiguous standalone surname: '{ent.canonical_name}' matches multiple distinct anchors "
                        f"{match_names}. Kept separate."
                    )
                    ent.evidence.append(ev)
                    ent.link_reasons.append(
                        EntityLinkReason(
                            rule="AMBIGUITY_SAFEGUARD",
                            source_variant=ent.canonical_name,
                            target_variant=", ".join(match_names),
                            score=0.40,
                            explanation=ev,
                        )
                    )

        # Stage 4: Phonetic Transliteration & Lexical Fuzzy Similarity (with Shared-Surname Safeguard)
        active_entities = [e for e in person_entities if e.entity_id not in merged_into]
        for i in range(len(active_entities)):
            ent_a = active_entities[i]
            if ent_a.entity_id in merged_into:
                continue
            parsed_a = NameComponents(ent_a.canonical_name)
            if not parsed_a.is_full_name:
                continue

            for j in range(i + 1, len(active_entities)):
                ent_b = active_entities[j]
                if ent_b.entity_id in merged_into:
                    continue
                parsed_b = NameComponents(ent_b.canonical_name)
                if not parsed_b.is_full_name:
                    continue

                # Safeguard 1: Never merge if first initials differ (e.g. Anil Kumar vs Sunil Kumar)
                if (
                    parsed_a.first_initial_char and parsed_b.first_initial_char
                    and parsed_a.first_initial_char != parsed_b.first_initial_char
                ):
                    continue

                first_a = (parsed_a.first_name or "").casefold()
                first_b = (parsed_b.first_name or "").casefold()
                last_a = (parsed_a.last_name or "").casefold()
                last_b = (parsed_b.last_name or "").casefold()

                first_sim = fuzz.ratio(first_a, first_b)
                last_sim = fuzz.ratio(last_a, last_b)
                full_sim = fuzz.token_sort_ratio(
                    " ".join(parsed_a.tokens).casefold(),
                    " ".join(parsed_b.tokens).casefold(),
                )
                phon_first_match = (_phonetic_key(first_a) == _phonetic_key(first_b)) and len(first_a) >= 4
                phon_last_match = (_phonetic_key(last_a) == _phonetic_key(last_b)) and len(last_a) >= 4

                # Safeguard 2: Shared surname alone NEVER establishes identity when given names are distinct
                # Require either:
                # (a) Identical given name + phonetic/high-fuzzy surname match (e.g. Aarav Choudhary vs Aarav Chaudhary), OR
                # (b) Identical surname + phonetic given-name match or high lexical typo similarity >= 88% on given name >= 5 chars
                is_safe_phonetic_or_typo = False
                rule_used = "FUZZY_TYPO_SIMILARITY"
                if first_a == first_b and (phon_last_match or last_sim >= 86):
                    is_safe_phonetic_or_typo = True
                    rule_used = "PHONETIC_TRANSLITERATION" if phon_last_match else "FUZZY_TYPO_SIMILARITY"
                elif last_a == last_b and (
                    (phon_first_match and first_sim >= 80)
                    or (first_sim >= 88 and min(len(first_a), len(first_b)) >= 5)
                ):
                    is_safe_phonetic_or_typo = True
                    rule_used = "PHONETIC_TRANSLITERATION" if phon_first_match else "FUZZY_TYPO_SIMILARITY"
                elif full_sim >= 91 and first_sim >= 86 and last_sim >= 86:
                    is_safe_phonetic_or_typo = True

                if is_safe_phonetic_or_typo:
                    target = ent_a if len(ent_a.canonical_name) >= len(ent_b.canonical_name) else ent_b
                    source = ent_b if target == ent_a else ent_a
                    merged_into[source.entity_id] = target.entity_id
                    evidence_str = (
                        f"Fuzzy lexical similarity ({full_sim:.1f}%, {rule_used}): "
                        f"linked '{source.canonical_name}' to '{target.canonical_name}'"
                    )
                    link_evidence.setdefault(target.entity_id, []).append(evidence_str)
                    link_reasons_map.setdefault(target.entity_id, []).append(
                        EntityLinkReason(
                            rule=rule_used,
                            source_variant=source.canonical_name,
                            target_variant=target.canonical_name,
                            score=round(full_sim / 100.0, 2),
                            explanation=evidence_str,
                        )
                    )
                    tier_map[target.entity_id] = ResolutionTier.PROBABLE_HEURISTIC.value
                elif full_sim >= 80 and last_a == last_b:
                    # Borderline similarity: record as non-merged confidence-aware suggestion for human review
                    suggestion = EntityLinkReason(
                        rule="SUGGESTED_FUZZY_LINK",
                        source_variant=ent_b.canonical_name,
                        target_variant=ent_a.canonical_name,
                        score=round(full_sim / 100.0, 2),
                        explanation=(
                            f"Borderline lexical similarity ({full_sim:.1f}%) between '{ent_b.canonical_name}' "
                            f"and '{ent_a.canonical_name}'; kept separate for human confirmation"
                        ),
                    )
                    ent_a.suggested_links.append(suggestion)
                    ent_b.suggested_links.append(suggestion)

        # Cycle-safe Union-Find transitive cluster consolidation
        entity_by_id: Dict[str, Entity] = {ent.entity_id: ent for ent in person_entities}

        def find_root(eid: str) -> str:
            curr = eid
            visited: Set[str] = set()
            while curr in merged_into and curr not in visited:
                visited.add(curr)
                curr = merged_into[curr]
            return curr

        surviving_entities: Dict[str, Entity] = {}
        for ent in person_entities:
            root_id = find_root(ent.entity_id)
            if root_id not in surviving_entities:
                surviving_entities[root_id] = entity_by_id[root_id]

        for ent in person_entities:
            root_id = find_root(ent.entity_id)
            target = surviving_entities[root_id]
            if target.entity_id != ent.entity_id:
                for cid in ent.candidate_ids:
                    if cid not in target.candidate_ids:
                        target.candidate_ids.append(cid)
                target.variants = sorted(list(set(target.variants + ent.variants)))
                if ent.is_ambiguous:
                    target.is_ambiguous = True
                    target.resolution_tier = ResolutionTier.AMBIGUOUS_CONFLICT.value
                # Accumulate any transitive evidence / link_reasons attached to intermediate nodes
                if ent.entity_id in link_evidence:
                    link_evidence.setdefault(root_id, []).extend(link_evidence.pop(ent.entity_id))
                if ent.entity_id in link_reasons_map:
                    link_reasons_map.setdefault(root_id, []).extend(link_reasons_map.pop(ent.entity_id))

        # Attach accumulated evidence and structured link_reasons
        for ent_id, target in surviving_entities.items():
            if ent_id in link_evidence:
                target.evidence.extend(link_evidence[ent_id])
                target.confidence = min(target.confidence, 0.85)
            if ent_id in link_reasons_map:
                target.link_reasons.extend(link_reasons_map[ent_id])
            if ent_id in tier_map and not target.is_ambiguous:
                target.resolution_tier = tier_map[ent_id]

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
            # Check if existing members of target_entity share a unanimous non-pending review decision
            existing_member_statuses = {
                cands_map[cid].review_status
                for cid in target_entity.candidate_ids
                if cid in cands_map and cands_map[cid].review_status in ("APPROVED", "REJECTED")
            }
            unanimous_status = (
                next(iter(existing_member_statuses))
                if len(existing_member_statuses) == 1
                else None
            )

            for cid in candidate_ids:
                if cid not in target_entity.candidate_ids:
                    target_entity.candidate_ids.append(cid)
            for c in selected_cands:
                if c.text not in target_entity.variants:
                    target_entity.variants.append(c.text)
                target_entity.link_reasons.append(
                    EntityLinkReason(
                        rule="USER_MANUAL_LINK",
                        source_variant=c.text,
                        target_variant=target_entity.canonical_name,
                        score=1.0,
                        explanation=f"Manually linked '{c.text}' to cluster '{target_entity.canonical_name}' by reviewer",
                    )
                )
                if unanimous_status and c.review_status == "PENDING":
                    c.review_status = unanimous_status
                    try:
                        record_review_decision(
                            doc_id=document_id,
                            cand_id=c.candidate_id,
                            decision=unanimous_status,
                            scope="LINKED_GROUP_PROPAGATION",
                        )
                    except Exception:
                        pass

            target_entity.evidence.append("User manual linkage")
            target_entity.resolution_tier = ResolutionTier.USER_DEFINED.value
            target_entity.is_user_defined = True
        else:
            # Create new entity cluster
            new_id = f"ent_{len(entities) + 1}"
            longest_name = max((c.text for c in selected_cands), key=len)
            # Propagate unanimous non-pending decision across newly merged cluster if present
            selected_statuses = {
                c.review_status for c in selected_cands if c.review_status in ("APPROVED", "REJECTED")
            }
            if len(selected_statuses) == 1:
                unanimous = next(iter(selected_statuses))
                for c in selected_cands:
                    if c.review_status == "PENDING":
                        c.review_status = unanimous
                        try:
                            record_review_decision(
                                doc_id=document_id,
                                cand_id=c.candidate_id,
                                decision=unanimous,
                                scope="LINKED_GROUP_PROPAGATION",
                            )
                        except Exception:
                            pass
            target_entity = Entity(
                entity_id=new_id,
                canonical_name=longest_name,
                entity_type=selected_cands[0].type,
                candidate_ids=list(dict.fromkeys(candidate_ids)),
                variants=sorted(list(set(c.text for c in selected_cands))),
                confidence=1.0,
                resolution_tier=ResolutionTier.USER_DEFINED.value,
                evidence=["User manual entity creation"],
                link_reasons=[
                    EntityLinkReason(
                        rule="USER_MANUAL_LINK",
                        source_variant=c.text,
                        target_variant=longest_name,
                        score=1.0,
                        explanation=f"Grouped '{c.text}' into manual cluster '{longest_name}'",
                    )
                    for c in selected_cands
                ],
                is_ambiguous=False,
                is_user_defined=True,
            )
            entities.append(target_entity)

        # Clean up any empty entities and re-index sequentially
        entities = [e for e in entities if len(e.candidate_ids) > 0]
        for idx, ent in enumerate(entities, start=1):
            ent.entity_id = f"ent_{idx}"

        cls._persist_resolution(document_id, entities, candidates)
        cls._invalidate_exports_on_cluster_change(session_dir)

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
        for idx, ent in enumerate(entities, start=1):
            ent.entity_id = f"ent_{idx}"
        cls._persist_resolution(document_id, entities, candidates)
        cls._invalidate_exports_on_cluster_change(get_safe_session_dir(document_id))

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
    def _invalidate_exports_on_cluster_change(cls, session_dir: Path) -> None:
        """Invalidate stale export and summary artifacts when entity clusters change."""
        for filename in ("export_metadata.json", "sanitized.txt", "sanitized.pdf", "summary.json"):
            p = session_dir / filename
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

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

        # Write entities.json atomically
        entities_path = session_dir / "entities.json"
        ent_data = [e.model_dump() for e in entities]
        atomic_write_text(entities_path, json.dumps(ent_data, indent=2), encoding="utf-8")

        # Write updated candidates.json atomically
        cands_path = session_dir / "candidates.json"
        cands_data = [c.model_dump() for c in candidates]
        atomic_write_text(cands_path, json.dumps(cands_data, indent=2), encoding="utf-8")

    @classmethod
    def save_entities(cls, document_id: str, entities: List[Entity]) -> None:
        """Save resolved entity clusters to session storage."""
        session_dir = get_safe_session_dir(document_id)
        entities_path = session_dir / "entities.json"
        ent_data = [e.model_dump() for e in entities]
        atomic_write_text(entities_path, json.dumps(ent_data, indent=2), encoding="utf-8")

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
        atomic_write_text(cands_path, json.dumps(cands_data, indent=2), encoding="utf-8")

    @classmethod
    def load_candidates(cls, document_id: str) -> List[Candidate]:
        """Load candidates from session storage."""
        session_dir = get_safe_session_dir(document_id)
        cands_path = session_dir / "candidates.json"
        if not cands_path.exists():
            return []
        raw = json.loads(cands_path.read_text(encoding="utf-8"))
        return [Candidate(**item) for item in raw]
