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

        # 3. Check page count
        page_count = doc.page_count
        if page_count == 0:
            doc.close()
            raise ValueError(f"PDF file '{filename}' contains no pages.")

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

            # Extract page text and normalize line breaks
            raw_page_text = page.get_text("text") or ""
            normalized_page_text = raw_page_text.replace("\r\n", "\n").replace("\r", "\n")

            # Page delimiter in canonical text
            if page_idx > 0:
                delimiter = "\n\n"
                canonical_text_parts.append(delimiter)
                current_offset += len(delimiter)

            page_start_offset = current_offset
            canonical_text_parts.append(normalized_page_text)
            current_offset += len(normalized_page_text)

            # Extract word bounding boxes: (x0, y0, x1, y1, word, block_no, line_no, word_no)
            words = page.get_text("words")
            total_word_count += len(words)

            if len(words) == 0 and len(image_list) > 0:
                warnings.append(f"Page {page_num} contains images but no extractable text.")

            # Map words to canonical character offsets
            search_idx = 0
            for w in words:
                x0, y0, x1, y1, word_str = float(w[0]), float(w[1]), float(w[2]), float(w[3]), str(w[4])
                # Locate in normalized_page_text
                idx = normalized_page_text.find(word_str, search_idx)
                if idx == -1:
                    # Retry search from beginning of page text if word ordering in 'words' deviated
                    idx = normalized_page_text.find(word_str)

                if idx != -1:
                    char_start = page_start_offset + idx
                    char_end = char_start + len(word_str)
                    coordinates.append(
                        CoordinateSpan(
                            page_number=page_num,
                            bbox=[round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                            char_start=char_start,
                            char_end=char_end,
                            text=word_str,
                        )
                    )
                    search_idx = idx + len(word_str)

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
