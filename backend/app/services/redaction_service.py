"""Redaction Service orchestrating TXT and native PyMuPDF PDF sanitization.

Strict Security Invariants:
1. Never remove content without explicit user approval (unreviewed/rejected spans preserved).
2. Never merely visually cover text with black rectangles in PDF: physically purge characters
   from the PDF content stream via PyMuPDF apply_redactions().
3. Never mutate original source document: read immutable canonical text / original.pdf.
4. Execute text replacement in strict descending offset order [start, end) on immutable text,
   with prior interval merging to resolve overlapping and contiguous approved spans.
5. Scrub all PDF metadata, embedded files, form field values, and link URIs.
6. Atomic output creation: write to .tmp, verify independently, promote only if PASSED.
   If verification fails, invalidate/remove any prior export files so stale verified exports
   can never be served.
7. If native PDF sanitization fails verification, block export and offer clean-text reconstruction (DEC-004).
"""

import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import pymupdf

from app.core.security import atomic_write_text, get_safe_session_dir
from app.database.session import get_document_metadata, update_document_status
from app.detectors.entity_resolver import EntityResolver
from app.schemas.candidate import Candidate
from app.schemas.document import CoordinateSpan
from app.schemas.entity import Entity
from app.schemas.redaction import (
    ExportState,
    PlaceholderStyle,
    RedactionRequest,
    RedactionResponse,
    VerificationResult,
)
from app.services.verification_service import VerificationService

logger = logging.getLogger(__name__)


class RedactionService:
    """Orchestrates document redaction for TXT and PDF documents with verifiable output guarantees."""

    @classmethod
    def redact_document(
        cls,
        document_id: str,
        request: Optional[RedactionRequest] = None,
    ) -> RedactionResponse:
        """Execute full redaction and post-export verification pipeline.

        Args:
            document_id: Unique session identifier.
            request: Optional redaction formatting configuration.

        Returns:
            RedactionResponse containing verification outcome and export readiness.
        """
        if request is None:
            request = RedactionRequest()

        meta = get_document_metadata(document_id)
        if not meta:
            raise ValueError(f"Document session '{document_id}' not found.")

        session_dir = get_safe_session_dir(document_id)
        canonical_path = session_dir / "canonical.txt"
        if not canonical_path.exists():
            raise FileNotFoundError(f"Canonical extracted text missing for session '{document_id}'.")

        # Invalidate / clean up any prior export files to prevent stale downloads if re-redaction fails
        cls._invalidate_existing_exports(session_dir)

        # Set persistent state to PROCESSING
        update_document_status(document_id, ExportState.PROCESSING.value)

        canonical_text = canonical_path.read_text(encoding="utf-8")
        candidates = EntityResolver.load_candidates(document_id)
        entities = EntityResolver.load_entities(document_id)

        approved_cands = [c for c in candidates if c.review_status == "APPROVED"]
        rejected_cands = [c for c in candidates if c.review_status == "REJECTED"]
        unreviewed_cands = [c for c in candidates if c.review_status == "PENDING"]

        file_type = meta["file_type"]
        export_filename = f"sanitized_{meta['original_filename']}"
        reconstructed_pdf_used = False
        reconstruction_offered = False
        layout_warning: Optional[str] = None

        sanitized_txt_tmp = session_dir / "sanitized.txt.tmp"
        sanitized_txt_final = session_dir / "sanitized.txt"
        sanitized_pdf_tmp = session_dir / "sanitized.pdf.tmp"
        sanitized_pdf_final = session_dir / "sanitized.pdf"

        # 1. Execute TXT Redaction to temporary file
        sanitized_text = cls.apply_txt_redaction(canonical_text, approved_cands, request)
        sanitized_txt_tmp.write_text(sanitized_text, encoding="utf-8")

        # 2. Execute PDF Redaction (if PDF)
        # DEC-004 Policy: Native PDF redaction is ALWAYS attempted first unless
        # the user explicitly selected clean-text reconstruction.
        if file_type == "pdf":
            if request.force_text_reconstruction:
                # Clean-text PDF reconstruction explicitly requested by user as alternative
                cls.reconstruct_pdf_from_text(sanitized_text, sanitized_pdf_tmp)
                reconstructed_pdf_used = True
                layout_warning = (
                    "Export generated via clean-text PDF reconstruction. Original graphical layout, "
                    "styling, and embedded images were omitted to guarantee verifiable privacy."
                )
            else:
                # Native PyMuPDF stream redaction attempted by default
                try:
                    cls.apply_native_pdf_redaction(
                        session_dir=session_dir,
                        output_pdf_path=sanitized_pdf_tmp,
                        approved_candidates=approved_cands,
                        all_candidates=candidates,
                    )
                except Exception as exc:
                    logger.warning("Native PyMuPDF redaction failed: %s", exc)
                    layout_warning = f"Native PDF redaction encountered an error: {str(exc)}"

        # 3. Post-Export Verification Audit on Temporary Files
        txt_verif_result = VerificationService.verify_txt_export(
            document_id=document_id,
            sanitized_txt_path=sanitized_txt_tmp,
            canonical_text=canonical_text,
            approved_candidates=approved_cands,
            all_candidates=candidates,
            entities=entities,
        )

        if file_type == "txt":
            verif_result = txt_verif_result
        else:
            if not sanitized_pdf_tmp.exists():
                verif_result = VerificationResult(
                    status="FAILED",
                    checks_run=["FILE_INTEGRITY"],
                    issues=[],
                    warnings=[layout_warning or "PDF redaction failed to produce output."],
                    verified_at="",
                )
            else:
                verif_result = VerificationService.verify_pdf_export(
                    document_id=document_id,
                    sanitized_pdf_path=sanitized_pdf_tmp,
                    approved_candidates=approved_cands,
                    all_candidates=candidates,
                    entities=entities,
                )
                # Also ensure companion TXT export passed verification
                if txt_verif_result.status != "PASSED":
                    verif_result.status = "FAILED"
                    verif_result.issues.extend(txt_verif_result.issues)

            # Security Correction: If native verification fails, fail closed, do NOT auto-reconstruct.
            # Instead, offer clean-text reconstruction as an explicit, separate user-triggered action.
            if verif_result.status == "FAILED" and not reconstructed_pdf_used:
                reconstruction_offered = True
                layout_warning = (
                    "Native PDF redaction verification failed: extractable sensitive content or unsupported structures "
                    "were detected. Export is blocked to prevent data leakage. You may explicitly trigger "
                    "'Clean-text PDF Reconstruction' as a separate safe alternative (note: original layout and "
                    "graphical formatting will not be preserved)."
                )

        # 4. Atomic Output Promotion or Invalidation
        export_sha256: Optional[str] = None
        if verif_result.status == "PASSED":
            export_state = ExportState.VERIFIED
            download_ready = True
            reconstruction_offered = False
            # Promote temp files atomically to final export files
            if sanitized_txt_tmp.exists():
                try:
                    sanitized_txt_tmp.replace(sanitized_txt_final)
                except PermissionError:
                    sanitized_txt_final.write_bytes(sanitized_txt_tmp.read_bytes())
                    sanitized_txt_tmp.unlink()
            if file_type == "pdf" and sanitized_pdf_tmp.exists():
                try:
                    sanitized_pdf_tmp.replace(sanitized_pdf_final)
                except PermissionError:
                    sanitized_pdf_final.write_bytes(sanitized_pdf_tmp.read_bytes())
                    sanitized_pdf_tmp.unlink()
            primary_final = sanitized_pdf_final if (file_type == "pdf" and sanitized_pdf_final.exists()) else sanitized_txt_final
            if primary_final.exists():
                export_sha256 = hashlib.sha256(primary_final.read_bytes()).hexdigest()
        else:
            export_state = ExportState.FAILED
            download_ready = False
            # Clean up all temporary files and ensure no partial or unverified final export exists
            if sanitized_txt_tmp.exists():
                sanitized_txt_tmp.unlink()
            if sanitized_pdf_tmp.exists():
                sanitized_pdf_tmp.unlink()
            cls._invalidate_existing_exports(session_dir)

        # Update SQLite document status
        update_document_status(document_id, export_state.value)

        # 5. Persist Export Metadata
        preview_length = min(300, len(sanitized_text))
        preview_str = sanitized_text[:preview_length]
        if len(sanitized_text) > preview_length:
            preview_str += "..."

        response = RedactionResponse(
            document_id=document_id,
            export_state=export_state,
            file_type=file_type,
            export_filename=export_filename,
            approved_redactions_applied=len(approved_cands),
            rejected_spans_preserved=len(rejected_cands),
            unreviewed_spans_preserved=len(unreviewed_cands),
            sanitized_text_preview=preview_str,
            verification=verif_result,
            download_ready=download_ready,
            reconstructed_pdf_used=reconstructed_pdf_used,
            reconstruction_offered=reconstruction_offered,
            layout_warning=layout_warning,
            export_sha256=export_sha256,
        )

        export_meta_path = session_dir / "export_metadata.json"
        atomic_write_text(export_meta_path, response.model_dump_json(indent=2), encoding="utf-8")

        return response

    @classmethod
    def apply_txt_redaction(
        cls,
        canonical_text: str,
        approved_candidates: List[Candidate],
        request: RedactionRequest,
    ) -> str:
        """Replace approved spans in canonical text with configurable placeholders.

        Rules:
        - Operates on immutable canonical text.
        - Validates all spans [start, end) against canonical text boundaries.
        - Merges overlapping or contiguous approved intervals into single contiguous zones.
        - Applies replacements in strict descending offset order.
        - Preserves all unapproved and rejected text untouched.
        """
        if not approved_candidates:
            return canonical_text

        text_len = len(canonical_text)
        valid_intervals: List[Dict[str, Any]] = []

        # Validate spans against canonical text length
        for c in approved_candidates:
            if not (0 <= c.start < c.end <= text_len):
                logger.warning(
                    "Invalid offset bounds [%d, %d) for text length %d (Candidate ID: %s) — skipped.",
                    c.start, c.end, text_len, c.candidate_id
                )
                continue
            valid_intervals.append({
                "start": c.start,
                "end": c.end,
                "type": c.type,
                "id": c.candidate_id,
                "entity_id": c.entity_id,
                "norm_text": c.text.strip().casefold(),
            })

        if not valid_intervals:
            return canonical_text

        # Sort intervals by start ASC, then end DESC to merge overlaps and assign stable entity indices
        valid_intervals.sort(key=lambda x: (x["start"], -x["end"]))

        # Build deterministic per-category entity index map in document appearance order
        # Never persisted to telemetry or logs
        category_counters: Dict[str, int] = {}
        entity_index_map: Dict[str, str] = {}
        if request.placeholder_style == PlaceholderStyle.ENTITY_INDEXED:
            for item in valid_intervals:
                cat = item["type"]
                ent_key = f"{cat}::ent::{item['entity_id']}" if item.get("entity_id") else f"{cat}::txt::{item['norm_text']}"
                if ent_key not in entity_index_map:
                    category_counters[cat] = category_counters.get(cat, 0) + 1
                    entity_index_map[ent_key] = f"{cat}_{category_counters[cat]}"

        merged_intervals: List[Dict[str, Any]] = []
        for item in valid_intervals:
            cat = item["type"]
            ent_key = f"{cat}::ent::{item['entity_id']}" if item.get("entity_id") else f"{cat}::txt::{item['norm_text']}"
            indexed_label = entity_index_map.get(ent_key, cat)
            if not merged_intervals:
                merged_intervals.append({
                    "start": item["start"],
                    "end": item["end"],
                    "types": [item["type"]],
                    "indexed_labels": [indexed_label],
                    "ids": [item["id"]],
                })
            else:
                prev = merged_intervals[-1]
                if item["start"] <= prev["end"]:
                    # Overlapping or contiguous approved spans: merge into single interval
                    prev["end"] = max(prev["end"], item["end"])
                    if item["type"] not in prev["types"]:
                        prev["types"].append(item["type"])
                    if indexed_label not in prev["indexed_labels"]:
                        prev["indexed_labels"].append(indexed_label)
                    prev["ids"].append(item["id"])
                else:
                    merged_intervals.append({
                        "start": item["start"],
                        "end": item["end"],
                        "types": [item["type"]],
                        "indexed_labels": [indexed_label],
                        "ids": [item["id"]],
                    })

        # Sort merged intervals in strict DESCENDING offset order to prevent index drift
        merged_intervals.sort(key=lambda x: x["start"], reverse=True)

        sanitized_chars = list(canonical_text)
        for interval in merged_intervals:
            labels = (
                interval["indexed_labels"]
                if request.placeholder_style == PlaceholderStyle.ENTITY_INDEXED
                else interval["types"]
            )
            placeholder = cls._resolve_placeholder(labels, request)
            start = interval["start"]
            end = interval["end"]
            sanitized_chars[start:end] = list(placeholder)

        return "".join(sanitized_chars)

    @classmethod
    def apply_native_pdf_redaction(
        cls,
        session_dir: Path,
        output_pdf_path: Optional[Path] = None,
        approved_candidates: Optional[List[Candidate]] = None,
        all_candidates: Optional[List[Candidate]] = None,
    ) -> None:
        """Physically redact approved text from original PDF using PyMuPDF.

        Occurrence-Safety Invariant:
        - Never redact an occurrence solely because its text matches an approved candidate when
          coordinate mappings exist or when rejected/pending occurrences share the text.
        - Preserve rejected and pending occurrences, including identical strings on the same page.
        - Fail closed (raise ValueError) if exact occurrence coordinates cannot be reliably established.
        """
        if output_pdf_path is None:
            output_pdf_path = session_dir / "sanitized.pdf"
        if approved_candidates is None:
            approved_candidates = []

        original_pdf_path = session_dir / "original.pdf"
        if not original_pdf_path.exists():
            raise FileNotFoundError(f"Original PDF file missing from session directory: {session_dir}")

        doc = pymupdf.open(original_pdf_path)

        # Load coordinate mappings if present
        coords_path = session_dir / "coordinates.json"
        has_coord_file = coords_path.exists()
        coords_list: List[CoordinateSpan] = []
        if has_coord_file:
            try:
                raw_coords = json.loads(coords_path.read_text(encoding="utf-8"))
                coords_list = [CoordinateSpan(**item) for item in raw_coords]
            except Exception as exc:
                doc.close()
                raise ValueError(f"Corrupted coordinates.json; failing closed: {exc}") from exc

        # Load all_candidates to identify rejected/pending spans that MUST be preserved
        if all_candidates is None:
            cands_path = session_dir / "candidates.json"
            if cands_path.exists():
                try:
                    raw_cands = json.loads(cands_path.read_text(encoding="utf-8"))
                    all_candidates = [Candidate(**c) for c in raw_cands]
                except Exception:
                    all_candidates = list(approved_candidates)
            else:
                all_candidates = list(approved_candidates)

        preserved_candidates = [
            c for c in all_candidates
            if c.review_status in ("REJECTED", "PENDING")
        ]

        # Build per-page list of preserved bounding boxes that must NEVER be redacted
        preserved_rects_by_page: Dict[int, List[pymupdf.Rect]] = {}
        for p_cand in preserved_candidates:
            p_page = getattr(p_cand, "page_number", None)
            if coords_list:
                for c in coords_list:
                    if (p_page is None or c.page_number == p_page) and not (
                        c.char_end <= p_cand.start or c.char_start >= p_cand.end
                    ):
                        preserved_rects_by_page.setdefault(c.page_number, []).append(
                            pymupdf.Rect(c.bbox[0], c.bbox[1], c.bbox[2], c.bbox[3])
                        )
            if p_cand.bbox and len(p_cand.bbox) == 4 and p_page is not None:
                preserved_rects_by_page.setdefault(p_page, []).append(
                    pymupdf.Rect(p_cand.bbox[0], p_cand.bbox[1], p_cand.bbox[2], p_cand.bbox[3])
                )

        # Track which approved candidates were matched in stream, widgets, links, metadata, or TOC
        matched_candidate_ids: Set[str] = set()

        # Check metadata / XMP / TOC upfront so metadata-only candidates are recognized
        meta_dict = doc.metadata or {}
        combined_meta_lower = " ".join(str(v) for v in meta_dict.values() if v).casefold()
        try:
            xml_meta_lower = (doc.get_xml_metadata() or "").casefold()
        except Exception:
            xml_meta_lower = ""

        for cand in approved_candidates:
            clean_c = cand.text.strip().casefold()
            if clean_c and (clean_c in combined_meta_lower or clean_c in xml_meta_lower):
                matched_candidate_ids.add(cand.candidate_id)

        try:
            for page_idx in range(doc.page_count):
                page = doc[page_idx]
                page_num = page_idx + 1
                page_preserved_rects = preserved_rects_by_page.get(page_num, [])

                for cand in approved_candidates:
                    clean_text = cand.text.strip()
                    if not clean_text:
                        continue

                    matched_rects: List[pymupdf.Rect] = []
                    cand_page = getattr(cand, "page_number", None)

                    # Strategy A: Authoritative offset-to-coordinate mapping
                    if cand_page is None or cand_page == page_num:
                        if coords_list:
                            overlapping_coords = [
                                c for c in coords_list
                                if c.page_number == page_num
                                and not (c.char_end <= cand.start or c.char_start >= cand.end)
                            ]
                            for c in overlapping_coords:
                                r = pymupdf.Rect(
                                    c.bbox[0] - 0.5,
                                    c.bbox[1] - 0.5,
                                    c.bbox[2] + 0.5,
                                    c.bbox[3] + 0.5,
                                )
                                matched_rects.append(r)

                        if not matched_rects and cand.bbox and len(cand.bbox) == 4:
                            if cand_page == page_num or (cand_page is None and doc.page_count == 1):
                                r = pymupdf.Rect(
                                    cand.bbox[0] - 0.5,
                                    cand.bbox[1] - 0.5,
                                    cand.bbox[2] + 0.5,
                                    cand.bbox[3] + 0.5,
                                )
                                matched_rects.append(r)

                    # Strategy B: Only permitted when no coordinates.json exists (synthetic unit tests),
                    # and strictly blocked if any preserved candidate shares/overlaps the surface string
                    # without disambiguating coordinates.
                    if not matched_rects and not has_coord_file:
                        if cand_page is not None and cand_page != page_num:
                            continue

                        clean_lower = clean_text.casefold()
                        ambiguous_preserved = [
                            p for p in preserved_candidates
                            if (clean_lower in p.text.strip().casefold() or p.text.strip().casefold() in clean_lower)
                            and not (p.bbox and len(p.bbox) == 4 and p.page_number is not None)
                        ]
                        if ambiguous_preserved:
                            raise ValueError(
                                f"Occurrence-safety violation: cannot disambiguate approved candidate "
                                f"'{cand.candidate_id}' from preserved occurrence without coordinate mappings."
                            )

                        search_rects = page.search_for(clean_text)
                        for sr in search_rects:
                            # Never redact a rect that overlaps with a preserved candidate's rect
                            overlaps_preserved = any(
                                sr.intersects(pr) for pr in page_preserved_rects
                            )
                            if not overlaps_preserved:
                                r = pymupdf.Rect(sr.x0 - 0.5, sr.y0 - 0.5, sr.x1 + 0.5, sr.y1 + 0.5)
                                matched_rects.append(r)

                    if matched_rects:
                        matched_candidate_ids.add(cand.candidate_id)

                    # Add actual redaction annotations
                    for rect in matched_rects:
                        page.add_redact_annot(rect, fill=(0, 0, 0))

                # Sanitize form widgets matching approved PII
                for widget in page.widgets():
                    field_val = str(widget.field_value or "")
                    for cand in approved_candidates:
                        if cand.text.strip().casefold() in field_val.casefold():
                            widget.field_value = "[REDACTED]"
                            widget.update()
                            matched_candidate_ids.add(cand.candidate_id)

                # Sanitize links with URIs matching approved PII
                links_to_delete = []
                for link in page.get_links():
                    uri = str(link.get("uri") or "").casefold()
                    for cand in approved_candidates:
                        clean_c = cand.text.strip().casefold()
                        if len(clean_c) >= 3 and clean_c in uri:
                            links_to_delete.append(link)
                            matched_candidate_ids.add(cand.candidate_id)
                            break
                for lk in links_to_delete:
                    page.delete_link(lk)

                # Physically delete text characters from the content stream
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)

            # Scrub document TOC / bookmark outlines containing approved PII
            try:
                toc = doc.get_toc()
                if toc:
                    toc_modified = False
                    for item in toc:
                        if len(item) >= 2 and isinstance(item[1], str):
                            title_str = item[1]
                            for cand in approved_candidates:
                                clean_c = cand.text.strip()
                                if len(clean_c) >= 2 and clean_c.casefold() in title_str.casefold():
                                    pat = re.compile(re.escape(clean_c), re.IGNORECASE)
                                    title_str = pat.sub("[REDACTED]", title_str)
                                    toc_modified = True
                                    matched_candidate_ids.add(cand.candidate_id)
                            item[1] = title_str
                    if toc_modified:
                        doc.set_toc(toc)
            except Exception as exc:
                logger.warning("Failed to scrub PDF TOC bookmarks: %s", exc)

            # Fail closed if coordinate mapping file existed and an approved candidate could not be located
            if has_coord_file:
                for cand in approved_candidates:
                    if cand.text.strip() and cand.candidate_id not in matched_candidate_ids:
                        raise ValueError(
                            f"Exact PDF occurrence coordinates could not be established for approved candidate "
                            f"'{cand.candidate_id}'; failing closed."
                        )

            # Scrub document metadata dictionaries and XMP XML metadata stream
            doc.set_metadata({})
            try:
                doc.del_xml_metadata()
            except Exception:
                pass

            # Delete embedded file attachments
            if doc.embfile_count() > 0:
                for emb_idx in range(doc.embfile_count() - 1, -1, -1):
                    doc.embfile_del(emb_idx)

            # Save clean, deflated output with unreferenced objects removed
            doc.save(
                output_pdf_path,
                garbage=4,
                deflate=True,
                clean=True,
            )
        finally:
            doc.close()

    @classmethod
    def reconstruct_pdf_from_text(
        cls,
        sanitized_text: str,
        output_pdf_path: Path,
    ) -> None:
        """Construct a new, clean layout PDF directly from sanitized text."""
        doc = pymupdf.open()
        margin = 50
        page_width, page_height = 595, 842  # Standard A4
        lines = sanitized_text.splitlines()
        current_page = doc.new_page(width=page_width, height=page_height)
        y = margin + 15
        line_height = 14

        for line in lines:
            if y + line_height > page_height - margin:
                current_page = doc.new_page(width=page_width, height=page_height)
                y = margin + 15

            if not line.strip():
                y += line_height
                continue

            # Wrap long lines cleanly
            words = line.split(" ")
            current_line = ""
            for word in words:
                test_line = f"{current_line} {word}".strip()
                if len(test_line) * 6 > (page_width - 2 * margin):
                    current_page.insert_text(
                        (margin, y),
                        current_line,
                        fontsize=10,
                        fontname="helv",
                    )
                    y += line_height
                    if y + line_height > page_height - margin:
                        current_page = doc.new_page(width=page_width, height=page_height)
                        y = margin + 15
                    current_line = word
                else:
                    current_line = test_line

            if current_line:
                current_page.insert_text(
                    (margin, y),
                    current_line,
                    fontsize=10,
                    fontname="helv",
                )
                y += line_height

        if doc.page_count == 0:
            doc.new_page(width=page_width, height=page_height)

        doc.set_metadata({})
        doc.save(output_pdf_path, garbage=4, deflate=True, clean=True)
        doc.close()

    @classmethod
    def _invalidate_existing_exports(cls, session_dir: Path) -> None:
        """Remove existing export files to prevent stale verified downloads if re-redaction fails."""
        for filename in ("sanitized.txt", "sanitized.pdf", "sanitized.txt.tmp", "sanitized.pdf.tmp"):
            fpath = session_dir / filename
            if fpath.exists():
                try:
                    fpath.unlink()
                except Exception as exc:
                    logger.warning("Could not unlink export file %s: %s", fpath, exc)

    @classmethod
    def _resolve_placeholder(
        cls,
        categories: List[str],
        request: RedactionRequest,
    ) -> str:
        """Resolve placeholder string based on requested style."""
        if request.placeholder_style == PlaceholderStyle.GENERIC:
            return "[REDACTED]"
        if request.placeholder_style == PlaceholderStyle.BLOCK:
            return "████████"
        if request.placeholder_style == PlaceholderStyle.CUSTOM and request.custom_placeholder:
            cat_str = "/".join(categories)
            return request.custom_placeholder.replace("{category}", cat_str)

        # Default: CATEGORY (e.g. [PERSON] or [PERSON/ID_LIKE])
        cat_label = "/".join(categories)
        return f"[{cat_label}]"
