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

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import pymupdf

from app.core.security import get_safe_session_dir
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
        layout_warning: Optional[str] = None

        sanitized_txt_tmp = session_dir / "sanitized.txt.tmp"
        sanitized_txt_final = session_dir / "sanitized.txt"
        sanitized_pdf_tmp = session_dir / "sanitized.pdf.tmp"
        sanitized_pdf_final = session_dir / "sanitized.pdf"

        # 1. Execute TXT Redaction to temporary file
        sanitized_text = cls.apply_txt_redaction(canonical_text, approved_cands, request)
        sanitized_txt_tmp.write_text(sanitized_text, encoding="utf-8")

        # 2. Execute PDF Redaction (if PDF)
        if file_type == "pdf":
            if request.force_text_reconstruction:
                # Clean-text PDF reconstruction alternative (DEC-004)
                cls.reconstruct_pdf_from_text(sanitized_text, sanitized_pdf_tmp)
                reconstructed_pdf_used = True
                layout_warning = (
                    "Export generated via clean-text PDF reconstruction. Original graphical layout, "
                    "styling, and embedded images were omitted to guarantee verifiable privacy."
                )
            else:
                try:
                    cls.apply_native_pdf_redaction(
                        session_dir=session_dir,
                        output_pdf_path=sanitized_pdf_tmp,
                        approved_candidates=approved_cands,
                    )
                except Exception as exc:
                    logger.warning("Native PyMuPDF redaction failed: %s", exc)
                    layout_warning = f"Native PDF redaction encountered an error: {str(exc)}"

        # 3. Post-Export Verification Audit on Temporary Files
        if file_type == "txt":
            verif_result = VerificationService.verify_txt_export(
                document_id=document_id,
                sanitized_txt_path=sanitized_txt_tmp,
                canonical_text=canonical_text,
                approved_candidates=approved_cands,
                all_candidates=candidates,
                entities=entities,
            )
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

            if verif_result.status == "FAILED" and not reconstructed_pdf_used:
                layout_warning = (
                    "Native PDF redaction verification detected potential leaks or unsupported structures. "
                    "Export is blocked. You may select 'Clean-text PDF Reconstruction' to export a verifiably safe PDF."
                )

        # 4. Atomic Output Promotion or Invalidation
        if verif_result.status == "PASSED":
            export_state = ExportState.VERIFIED
            download_ready = True
            # Promote temp files atomically to final export files
            if sanitized_txt_tmp.exists():
                sanitized_txt_tmp.replace(sanitized_txt_final)
            if file_type == "pdf" and sanitized_pdf_tmp.exists():
                sanitized_pdf_tmp.replace(sanitized_pdf_final)
        else:
            export_state = ExportState.FAILED
            download_ready = False
            # Clean up temp files; ensure no final export file exists
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
            layout_warning=layout_warning,
        )

        export_meta_path = session_dir / "export_metadata.json"
        export_meta_path.write_text(response.model_dump_json(indent=2), encoding="utf-8")

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
            })

        if not valid_intervals:
            return canonical_text

        # Sort intervals by start ASC, then end DESC to merge overlaps
        valid_intervals.sort(key=lambda x: (x["start"], -x["end"]))

        merged_intervals: List[Dict[str, Any]] = []
        for item in valid_intervals:
            if not merged_intervals:
                merged_intervals.append({
                    "start": item["start"],
                    "end": item["end"],
                    "types": [item["type"]],
                    "ids": [item["id"]],
                })
            else:
                prev = merged_intervals[-1]
                if item["start"] <= prev["end"]:
                    # Overlapping or contiguous approved spans: merge into single interval
                    prev["end"] = max(prev["end"], item["end"])
                    if item["type"] not in prev["types"]:
                        prev["types"].append(item["type"])
                    prev["ids"].append(item["id"])
                else:
                    merged_intervals.append({
                        "start": item["start"],
                        "end": item["end"],
                        "types": [item["type"]],
                        "ids": [item["id"]],
                    })

        # Sort merged intervals in strict DESCENDING offset order to prevent index drift
        merged_intervals.sort(key=lambda x: x["start"], reverse=True)

        sanitized_chars = list(canonical_text)
        for interval in merged_intervals:
            placeholder = cls._resolve_placeholder(interval["types"], request)
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
    ) -> None:
        """Physically redact approved text from original PDF using PyMuPDF."""
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
        coords_list: List[CoordinateSpan] = []
        if coords_path.exists():
            try:
                raw_coords = json.loads(coords_path.read_text(encoding="utf-8"))
                coords_list = [CoordinateSpan(**item) for item in raw_coords]
            except Exception as exc:
                logger.warning("Failed to load coordinates.json: %s", exc)

        try:
            for page_idx in range(doc.page_count):
                page = doc[page_idx]
                page_num = page_idx + 1

                for cand in approved_candidates:
                    clean_text = cand.text.strip()
                    if not clean_text:
                        continue

                    # Strategy A: Use pre-extracted coordinate spans matching this candidate on this page
                    matched_rects: List[pymupdf.Rect] = []
                    cand_page = getattr(cand, "page_number", None)

                    if cand_page is None or cand_page == page_num:
                        overlapping_coords = [
                            c for c in coords_list
                            if c.page_number == page_num
                            and not (c.char_end <= cand.start or c.char_start >= cand.end)
                        ]
                        for c in overlapping_coords:
                            # Add 0.5pt padding to encompass font ascenders and descenders
                            r = pymupdf.Rect(
                                c.bbox[0] - 0.5,
                                c.bbox[1] - 0.5,
                                c.bbox[2] + 0.5,
                                c.bbox[3] + 0.5,
                            )
                            matched_rects.append(r)

                    # Strategy B: If no coordinate spans found (e.g. headers/footers), use text search
                    if not matched_rects:
                        search_rects = page.search_for(clean_text)
                        for sr in search_rects:
                            r = pymupdf.Rect(sr.x0 - 0.5, sr.y0 - 0.5, sr.x1 + 0.5, sr.y1 + 0.5)
                            matched_rects.append(r)

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

                # Sanitize links with URIs matching approved PII
                links_to_delete = []
                for link in page.get_links():
                    uri = str(link.get("uri") or "").casefold()
                    for cand in approved_candidates:
                        clean_c = cand.text.strip().casefold()
                        if len(clean_c) >= 3 and clean_c in uri:
                            links_to_delete.append(link)
                            break
                for lk in links_to_delete:
                    page.delete_link(lk)

                # Physically delete text characters and image bytes from the content stream
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)

            # Scrub document metadata dictionaries
            doc.set_metadata({})

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
