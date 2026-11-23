"""TXT Document Processor.

Extracts canonical text using UTF-8 decoding with documented fallback encodings.
Preserves Unicode code-point offsets.
"""

from typing import List, Tuple


class TXTProcessor:
    """Extracts and normalizes text from plain text files."""

    FALLBACK_ENCODINGS = ["utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]

    @classmethod
    def extract(cls, content_bytes: bytes, filename: str = "document.txt") -> Tuple[str, List[str]]:
        """Extract canonical text from bytes.
        
        Args:
            content_bytes: Raw bytes of the uploaded text file.
            filename: Original filename for logging/warning context.
            
        Returns:
            Tuple of (canonical_text, list_of_warnings).
            
        Raises:
            ValueError: If file is empty or cannot be decoded.
        """
        if not content_bytes or len(content_bytes) == 0:
            raise ValueError(f"File '{filename}' is empty (0 bytes).")

        warnings: List[str] = []
        decoded_text: str = ""
        used_encoding = "utf-8"

        # 1. Primary UTF-8 decoding attempt
        try:
            decoded_text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # 2. Documented fallback sequence
            fallback_success = False
            for enc in cls.FALLBACK_ENCODINGS:
                try:
                    decoded_text = content_bytes.decode(enc)
                    used_encoding = enc
                    fallback_success = True
                    warnings.append(
                        f"File '{filename}' is not valid UTF-8. Decoded successfully using '{enc}' fallback."
                    )
                    break
                except UnicodeDecodeError:
                    continue

            if not fallback_success:
                raise ValueError(
                    f"File '{filename}' could not be decoded as UTF-8 or any standard fallback ({cls.FALLBACK_ENCODINGS})."
                )

        # 3. Canonical newline, invisible zero-width/bidi removal, and Unicode space normalization
        from app.core.security import MAX_EXTRACTED_CHARS, strip_invisible_and_normalize_whitespace
        canonical_text = decoded_text.replace("\r\n", "\n").replace("\r", "\n")
        canonical_text = strip_invisible_and_normalize_whitespace(canonical_text)

        if len(canonical_text) > MAX_EXTRACTED_CHARS:
            raise ValueError(
                f"File '{filename}' exceeds maximum permitted extracted text length ({MAX_EXTRACTED_CHARS} characters)."
            )

        # 4. Check for empty/whitespace-only content
        if not canonical_text.strip():
            raise ValueError(f"File '{filename}' contains no readable text (whitespace only).")

        return canonical_text, warnings
