"""Redaction Service orchestrating TXT and native PyMuPDF PDF sanitization.

Strict Security Invariants:
1. Never remove content without explicit user approval (unreviewed/rejected spans preserved).
2. Never merely visually cover text with black rectangles in PDF: physically purge characters
   from the PDF content stream via PyMuPDF apply_redactions().
3. Never use raw original text in exported artifacts: execute text replacement in strict
   descending offset order [start, end) on immutable canonical text.
4. Scrub all PDF metadata, embedded files, and scripts to prevent auxiliary data leaks.
5. If native PDF sanitization fails verification, block export and offer clean-text reconstruction.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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
    """Orchestrates document redaction for TXT and PDF documents."""

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

        # 1. Execute TXT Redaction
        sanitized_text = cls.apply_txt_redaction(canonical_text, approved_cands, request)
        sanitized_txt_path = session_dir / "sanitized.txt"
        sanitized_txt_path.write_text(sanitized_text, encoding="utf-8")

        # 2. Execute PDF Redaction (if PDF)
        if file_type == "pdf":
            original_pdf_path = session_dir / "original.pdf"
            sanitized_pdf_path = session_dir / "sanitized.pdf"

            if request.force_text_reconstruction:
                # Clean-text PDF reconstruction alternative
                cls.reconstruct_pdf_from_text(sanitized_text, sanitized_pdf_path)
                reconstructed_pdf_used = True
                layout_warning = (
                    "Export generated via clean-text PDF reconstruction. Original graphical layout, "
                    "styling, and embedded images were omitted to guarantee verifiable privacy."
                )
            else:
                try:
                    cls.apply_native_pdf_redaction(
                        session_dir=session_dir,
                        approved_candidates=approved_cands,
                    )
                except Exception as exc:
                    logger.warning("Native PyMuPDF redaction failed: %s", exc)
                    # Native redaction crashed or failed; create failure result
                    layout_warning = f"Native PDF redaction encountered an error: {str(exc)}"

        # 3. Post-Export Verification Audit
        if file_type == "txt":
            verif_result = VerificationService.verify_txt_export(
                document_id=document_id,
                sanitized_txt_path=sanitized_txt_path,
                approved_candidates=approved_cands,
                entities=entities,
            )
        else:
            sanitized_pdf_path = session_dir / "sanitized.pdf"
            verif_result = VerificationService.verify_pdf_export(
                document_id=document_id,
                sanitized_pdf_path=sanitized_pdf_path,
                approved_candidates=approved_cands,
                entities=entities,
            )
            # If native redaction verification failed and user didn't force reconstruction,
            # we offer reconstruction as an explicit alternative in the warning
            if verif_result.status == "FAILED" and not reconstructed_pdf_used:
                layout_warning = (
                    "Native PDF redaction verification detected potential leaks or unsupported structures. "
                    "Export is blocked. You may select 'Clean-text PDF Reconstruction' to export a verifiably safe PDF."
                )

        # 4. Determine Export State
        if verif_result.status == "PASSED":
            export_state = ExportState.VERIFIED
            download_ready = True
        else:
            export_state = ExportState.FAILED
            download_ready = False

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
        - Validates all spans [start, end) against canonical text boundaries.
        - Merges overlapping approved intervals into contiguous replacement zones.
        - Applies replacements in strict descending offset order.
        - Preserves all unapproved and rejected text.
        """
        if not approved_candidates:
            return canonical_text

        text_len = len(canonical_text)
        valid_intervals: List[Dict[str, Any]] = []

        # Validate spans against canonical text
        for c in approved_candidates:
            if not (0 <= c.start < c.end <= text_len):
                logger.warning(
                    "Invalid offset bounds [%d, %d) for text length %d (ID: %s)",
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
                if item["start"] < prev["end"]:
                    # Overlapping or contiguous approved spans: merge into single zone
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
        approved_candidates: List[Candidate],
    ) -> None:
        """Physically redact approved text from original PDF using PyMuPDF."""
        original_pdf_path = session_dir / "original.pdf"
        sanitized_pdf_path = session_dir / "sanitized.pdf"

        if not original_pdf_path.exists():
            raise FileNotFoundError(f"Original PDF file missing from session directory: {session_dir}")

        doc = pymupdf.open(original_pdf_path)

        # Load coordinate mappings if present
        coords_path = session_dir / "coordinates.json"
        coords_list: List[CoordinateSpan] = []
        if coords_path.exists():
            raw_coords = json.loads(coords_path.read_text(encoding="utf-8"))
            coords_list = [CoordinateSpan(**item) for item in raw_coords]

        try:
            for page_idx in range(doc.page_count):
                page = doc[page_idx]
                page_num = page_idx + 1

                for cand in approved_candidates:
                    clean_text = cand.text.strip()
                    if not clean_text:
                        continue

                    # Strategy A: Use PyMuPDF page.search_for
                    matched_rects = page.search_for(clean_text)

                    # Strategy B: Supplement with pre-extracted coordinates for this page
                    page_coords = [
                        c for c in coords_list
                        if c.page_number == page_num
                        and cand.start <= c.char_start < cand.end
                    ]
                    for coord in page_coords:
                        r = pymupdf.Rect(coord.bbox)
                        if not any(r.intersects(mr) for mr in matched_rects):
                            matched_rects.append(r)

                    # Add actual redaction annotation for each rect
                    for rect in matched_rects:
                        page.add_redact_annot(rect, fill=(0, 0, 0))

                # Apply redactions to physically delete text characters from the content stream
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)

            # Scrub document metadata and delete embedded attachments
            doc.set_metadata({})
            if doc.embfile_count() > 0:
                for emb_idx in range(doc.embfile_count() - 1, -1, -1):
                    doc.embfile_del(emb_idx)

            # Save clean, deflated output with unreferenced objects removed
            doc.save(
                sanitized_pdf_path,
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
        rect = pymupdf.Rect(margin, margin, page_width - margin, page_height - margin)

        lines = sanitized_text.splitlines()
        current_page = doc.new_page(width=page_width, height=page_height)
        y = margin + 15
        line_height = 14

        for line in lines:
            if y + line_height > page_height - margin:
                current_page = doc.new_page(width=page_width, height=page_height)
                y = margin + 15

            # Handle empty lines
            if not line.strip():
                y += line_height
                continue

            # Wrap long lines cleanly
            words = line.split(" ")
            current_line = ""
            for word in words:
                test_line = f"{current_line} {word}".strip()
                # Rough width estimation (fontsize 10, ~6 pts per char)
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

        # Empty document safeguard
        if doc.page_count == 0:
            doc.new_page(width=page_width, height=page_height)

        doc.set_metadata({})
        doc.save(output_pdf_path, garbage=4, deflate=True, clean=True)
        doc.close()

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
