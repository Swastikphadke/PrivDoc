"""Detection Service orchestrating Regex, NER, and contextual detectors.

Performs deterministic candidate normalization, duplicate merging, provenance
retention, and coordinate enrichment for PDF documents.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from app.core.security import get_safe_session_dir
from app.detectors.ner_detector import NERDetector
from app.detectors.regex_detector import RegexDetector
from app.schemas.candidate import Candidate, ConfidenceBand, DetectionResponse


class DetectionService:
    """Orchestrates PII detection engines and merges candidates deterministically."""

    @classmethod
    def run_detection(cls, document_id: str) -> DetectionResponse:
        """Execute detection pipeline for an active document session.

        Args:
            document_id: Session identifier.

        Returns:
            DetectionResponse containing normalized candidates and execution stats.
        """
        start_time = time.perf_counter()
        session_dir = get_safe_session_dir(document_id)
        canonical_path = session_dir / "canonical.txt"

        if not canonical_path.exists():
            raise FileNotFoundError(f"Canonical text not found for session '{document_id}'.")

        text = canonical_path.read_text(encoding="utf-8")

        # 1. Run independent detector engines
        raw_candidates: List[Candidate] = []
        detectors_run = [RegexDetector.DETECTOR_NAME, NERDetector.DETECTOR_NAME]

        # Engine A: Regex
        regex_cands = RegexDetector.detect(text, document_id)
        raw_candidates.extend(regex_cands)

        # Engine B: NER / Contextual
        ner_cands = NERDetector.detect(text, document_id)
        raw_candidates.extend(ner_cands)

        # 2. Deterministic candidate merging & conflict handling
        merged_candidates = cls.merge_candidates(raw_candidates, text, document_id)

        # 3. Enrich with PDF coordinates if available
        coords_path = session_dir / "coordinates.json"
        if coords_path.exists():
            cls._enrich_coordinates(merged_candidates, coords_path)

        # 4. Resolve entities across candidates
        from app.detectors.entity_resolver import EntityResolver
        EntityResolver.resolve_entities(
            document_id=document_id,
            candidates=merged_candidates,
            canonical_text=text,
            use_slm=True,
        )

        # 5. Save candidates to session cache (candidates now have entity_id attached)
        candidates_cache_path = session_dir / "candidates.json"
        cands_data = [c.model_dump() for c in merged_candidates]
        candidates_cache_path.write_text(json.dumps(cands_data, indent=2), encoding="utf-8")

        exec_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return DetectionResponse(
            document_id=document_id,
            total_candidates=len(merged_candidates),
            candidates=merged_candidates,
            execution_time_ms=exec_ms,
            detectors_run=detectors_run,
        )

    @classmethod
    def detect_from_text(
        cls,
        text: str,
        document_id: str = "eval_doc",
        resolve_entities: bool = True,
    ) -> List[Candidate]:
        """Directly run detection pipeline on canonical text string (for evaluation and tests)."""
        raw_candidates: List[Candidate] = []
        raw_candidates.extend(RegexDetector.detect(text, document_id))
        raw_candidates.extend(NERDetector.detect(text, document_id))

        merged = cls.merge_candidates(raw_candidates, text, document_id)

        if resolve_entities:
            from app.detectors.entity_resolver import EntityResolver
            EntityResolver.resolve_entities(
                document_id=document_id,
                candidates=merged,
                canonical_text=text,
                use_slm=False,
            )

        return merged

    @classmethod
    def merge_candidates(
        cls,
        raw_candidates: List[Candidate],
        text: str,
        document_id: str
    ) -> List[Candidate]:
        """Merge duplicate and overlapping spans deterministically while preserving provenance.

        Rules:
        - Exact duplicate spans: merge sources, take highest confidence (with agreement boost).
        - Subsumed spans of same type: expand to larger span, merge sources.
        - Conflicting types on overlapping spans: retain both so human reviewer can decide.
        """
        if not raw_candidates:
            return []

        # Sort candidates primarily by start offset ascending, then by length descending
        sorted_cands = sorted(
            raw_candidates,
            key=lambda c: (c.start, -(c.end - c.start), c.type)
        )

        merged: List[Candidate] = []
        for cand in sorted_cands:
            matched_existing = False
            for existing in merged:
                # 1. Exact Duplicate Span
                if existing.start == cand.start and existing.end == cand.end:
                    if existing.type == cand.type:
                        # Combine detector sources without duplicates
                        for s in cand.sources:
                            if s not in existing.sources:
                                existing.sources.append(s)
                        # Multi-detector agreement boost (+0.05, max 0.99)
                        max_c = max(existing.confidence, cand.confidence)
                        boosted = min(0.99, max_c + 0.05) if len(existing.sources) > 1 else max_c
                        existing.confidence = round(boosted, 2)
                        existing.confidence_band = cls._get_confidence_band(existing.confidence)
                        matched_existing = True
                        break
                    # If exact span has conflicting types, do NOT overwrite; keep both for human review

                # 2. Complete Subsumption of Same Category (e.g. "Richa" inside "Richa Sharma")
                elif existing.start <= cand.start and existing.end >= cand.end:
                    if existing.type == cand.type:
                        for s in cand.sources:
                            if s not in existing.sources:
                                existing.sources.append(s)
                        matched_existing = True
                        break

            if not matched_existing:
                merged.append(cand)

        # Re-index candidate IDs sequentially
        for idx, c in enumerate(merged, start=1):
            c.candidate_id = f"c_{idx:04d}"

        return merged

    @classmethod
    def _enrich_coordinates(cls, candidates: List[Candidate], coords_path: Path) -> None:
        """Map canonical offsets of candidates to PDF coordinates."""
        try:
            raw_coords = json.loads(coords_path.read_text(encoding="utf-8"))
            if not raw_coords:
                return

            for cand in candidates:
                # Find all word spans intersecting with candidate [start, end)
                matching_spans = [
                    item for item in raw_coords
                    if not (item["char_end"] <= cand.start or item["char_start"] >= cand.end)
                ]

                if matching_spans:
                    # Take page number from first matching span
                    cand.page_number = matching_spans[0]["page_number"]
                    # Calculate bounding box union: [min_x0, min_y0, max_x1, max_y1]
                    min_x0 = min(s["bbox"][0] for s in matching_spans)
                    min_y0 = min(s["bbox"][1] for s in matching_spans)
                    max_x1 = max(s["bbox"][2] for s in matching_spans)
                    max_y1 = max(s["bbox"][3] for s in matching_spans)
                    cand.bbox = [round(min_x0, 2), round(min_y0, 2), round(max_x1, 2), round(max_y1, 2)]
        except Exception:
            pass

    @staticmethod
    def _get_confidence_band(conf: float) -> str:
        if conf >= 0.85:
            return ConfidenceBand.HIGH.value
        elif conf >= 0.60:
            return ConfidenceBand.MEDIUM.value
        return ConfidenceBand.LOW.value
