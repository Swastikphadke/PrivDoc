"""PDF Document Processor using PyMuPDF.

Extracts canonical text, page-level text, and word/span bounding boxes.
Maps canonical Unicode character offsets to PDF coordinates.
Detects empty, malformed, encrypted, and image-only/scanned PDFs.
"""

from typing import List, Tuple, Dict, Any
import pymupdf
from app.schemas.document import CoordinateSpan


class PDFProcessor:
    """Extracts text and coordinate geometries from text-based PDF documents."""

    @classmethod
    def extract(
        cls,
        content_bytes: bytes,
        filename: str = "document.pdf"
    ) -> Tuple[str, int, List[CoordinateSpan], List[str]]:
        """Extract canonical text and coordinate mappings from raw PDF bytes.

        Args:
            content_bytes: Raw bytes of the uploaded PDF.
            filename: Original filename for logging and error reporting.

        Returns:
            Tuple of:
                - canonical_text: Concatenated plain text across pages.
                - page_count: Total number of pages.
                - coordinates: List of CoordinateSpan objects mapping text to bboxes.
                - warnings: Extraction notes/warnings.

        Raises:
            ValueError: If PDF is empty, malformed, password-protected, or image-only.
        """
        if not content_bytes or len(content_bytes) == 0:
            raise ValueError(f"File '{filename}' is empty (0 bytes).")

        # 1. Open document safely
        try:
            doc = pymupdf.open(stream=content_bytes, filetype="pdf")
        except Exception as exc:
            raise ValueError(f"Malformed or corrupted PDF file '{filename}': {str(exc)}") from exc

        # 2. Check encryption / password protection
        if doc.is_encrypted or doc.needs_pass:
            doc.close()
            raise ValueError(
                f"File '{filename}' is password-protected or encrypted. Encrypted PDFs are not supported."
            )

        # 3. Check page count and resource exhaustion bounds
        from app.core.security import (
            MAX_EXTRACTED_CHARS,
            MAX_PDF_PAGES,
            strip_invisible_and_normalize_whitespace,
        )
        page_count = doc.page_count
        if page_count == 0:
            doc.close()
            raise ValueError(f"PDF file '{filename}' contains no pages.")
        if page_count > MAX_PDF_PAGES:
            doc.close()
            raise ValueError(
                f"PDF file '{filename}' contains {page_count} pages, exceeding maximum limit of {MAX_PDF_PAGES} pages."
            )

        canonical_text_parts: List[str] = []
        coordinates: List[CoordinateSpan] = []
        warnings: List[str] = []

        total_word_count = 0
        total_image_count = 0
        current_offset = 0

        # 4. Iterate over pages
        for page_idx in range(page_count):
            page = doc[page_idx]
            page_num = page_idx + 1

            # Count embedded images
            image_list = page.get_images()
            total_image_count += len(image_list)

            # Extract page text, strip invisible control chars, and normalize line breaks
            raw_page_text = page.get_text("text") or ""
            normalized_page_text = strip_invisible_and_normalize_whitespace(
                raw_page_text.replace("\r\n", "\n").replace("\r", "\n")
            )

            # Page delimiter in canonical text
            if page_idx > 0:
                delimiter = "\n\n"
                canonical_text_parts.append(delimiter)
                current_offset += len(delimiter)

            page_start_offset = current_offset
            canonical_text_parts.append(normalized_page_text)
            current_offset += len(normalized_page_text)
            if current_offset > MAX_EXTRACTED_CHARS:
                doc.close()
                raise ValueError(
                    f"PDF file '{filename}' exceeds maximum extracted text length ({MAX_EXTRACTED_CHARS} characters)."
                )

            # Extract word bounding boxes: (x0, y0, x1, y1, word, block_no, line_no, word_no)
            words = page.get_text("words")
            total_word_count += len(words)

            if len(words) == 0 and len(image_list) > 0:
                warnings.append(f"Page {page_num} contains images but no extractable text.")

            # Extract page geometry (accounting for rotation and cropbox)
            p_rect = page.rect
            p_x0 = round(float(p_rect.x0), 2)
            p_y0 = round(float(p_rect.y0), 2)
            p_width = round(float(p_rect.width), 2) if p_rect.width > 0 else 595.0
            p_height = round(float(p_rect.height), 2) if p_rect.height > 0 else 842.0
            p_rot = int(getattr(page, "rotation", 0) or 0)

            # Map words to canonical character offsets monotonically without resetting to 0
            search_idx = 0
            claimed_intervals: List[Tuple[int, int]] = []
            for w in words:
                x0, y0, x1, y1 = float(w[0]), float(w[1]), float(w[2]), float(w[3])
                word_str = strip_invisible_and_normalize_whitespace(str(w[4])).strip()
                if not word_str:
                    continue

                # 1. Primary monotonic forward search from search_idx
                idx = normalized_page_text.find(word_str, search_idx)

                # 2. If block/column ordering caused minor local inversion, search a bounded local window
                if idx == -1 or idx > search_idx + 120:
                    win_start = max(0, search_idx - 60)
                    win_end = min(len(normalized_page_text), search_idx + 200)
                    scan_pos = win_start
                    found_local = -1
                    while scan_pos < win_end:
                        cand_idx = normalized_page_text.find(word_str, scan_pos, win_end)
                        if cand_idx == -1:
                            break
                        cand_end = cand_idx + len(word_str)
                        already_claimed = any(
                            not (cand_end <= c_s or cand_idx >= c_e)
                            for c_s, c_e in claimed_intervals
                        )
                        if not already_claimed:
                            found_local = cand_idx
                            break
                        scan_pos = cand_idx + 1
                    if found_local != -1:
                        idx = found_local

                if idx != -1:
                    char_start = page_start_offset + idx
                    char_end = char_start + len(word_str)
                    claimed_intervals.append((idx, idx + len(word_str)))
                    coordinates.append(
                        CoordinateSpan(
                            page_number=page_num,
                            bbox=[round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                            char_start=char_start,
                            char_end=char_end,
                            text=word_str,
                            page_x0=p_x0,
                            page_y0=p_y0,
                            page_width=p_width,
                            page_height=p_height,
                            page_rotation=p_rot,
                        )
                    )
                    # Monotonic progress: never move search_idx backward
                    search_idx = max(search_idx, idx + len(word_str))

        doc.close()

        canonical_text = "".join(canonical_text_parts)

        # 5. Detect image-only / scanned PDF
        if total_word_count == 0 or len(canonical_text.strip()) == 0:
            if total_image_count > 0:
                raise ValueError(
                    f"File '{filename}' is an image-only or scanned PDF without digital text. OCR is out of scope."
                )
            raise ValueError(f"File '{filename}' contains no readable digital text.")

        return canonical_text, page_count, coordinates, warnings
