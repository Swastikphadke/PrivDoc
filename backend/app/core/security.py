"""Security controls, file validation, Unicode adversarial normalization, and path protections."""

import os
import re
import shutil
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Dict, Set
from fastapi import HTTPException, status
from app.core.config import settings


ALLOWED_EXTENSIONS: Set[str] = {".txt", ".pdf"}
PDF_MAGIC_BYTES: bytes = b"%PDF-"
MAX_PDF_PAGES: int = 500
MAX_EXTRACTED_CHARS: int = 2_000_000

# Invisible zero-width, soft-hyphen, and bidirectional spoofing control characters
INVISIBLE_CONTROL_REGEX = re.compile(
    r"[\u00ad\u034f\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]"
)
# Exotic horizontal Unicode spaces (NBSP, En/Em/Thin/Ideographic spaces) -> standard ASCII space
UNICODE_SPACE_REGEX = re.compile(
    r"[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]"
)

# 1-to-1 single-codepoint Cyrillic and Greek confusable homoglyphs -> Latin ASCII
HOMOGLYPH_MAP: Dict[str, str] = {
    "\u0430": "a",  # Cyrillic small a
    "\u0435": "e",  # Cyrillic small ie
    "\u043e": "o",  # Cyrillic small o
    "\u0440": "p",  # Cyrillic small er
    "\u0441": "c",  # Cyrillic small es
    "\u0443": "y",  # Cyrillic small u
    "\u0445": "x",  # Cyrillic small ha
    "\u0456": "i",  # Cyrillic small byelorussian-ukrainian i
    "\u0458": "j",  # Cyrillic small je
    "\u0455": "s",  # Cyrillic small dze
    "\u0501": "d",  # Cyrillic small komi de
    "\u0410": "A",  # Cyrillic capital A
    "\u0412": "B",  # Cyrillic capital VE
    "\u0415": "E",  # Cyrillic capital IE
    "\u041a": "K",  # Cyrillic capital KA
    "\u041c": "M",  # Cyrillic capital EM
    "\u041d": "H",  # Cyrillic capital EN
    "\u041e": "O",  # Cyrillic capital O
    "\u0420": "P",  # Cyrillic capital ER
    "\u0421": "C",  # Cyrillic capital ES
    "\u0422": "T",  # Cyrillic capital TE
    "\u0425": "X",  # Cyrillic capital HA
    "\u0406": "I",  # Cyrillic capital I
    "\u0405": "S",  # Cyrillic capital DZE
    "\u03b1": "a",  # Greek small alpha
    "\u03b5": "e",  # Greek small epsilon
    "\u03bf": "o",  # Greek small omicron
    "\u03c1": "p",  # Greek small rho
    "\u0391": "A",  # Greek capital Alpha
    "\u0392": "B",  # Greek capital Beta
    "\u0395": "E",  # Greek capital Epsilon
    "\u0397": "H",  # Greek capital Eta
    "\u0399": "I",  # Greek capital Iota
    "\u039a": "K",  # Greek capital Kappa
    "\u039c": "M",  # Greek capital Mu
    "\u039d": "N",  # Greek capital Nu
    "\u039f": "O",  # Greek capital Omicron
    "\u03a1": "P",  # Greek capital Rho
    "\u03a4": "T",  # Greek capital Tau
    "\u03a7": "X",  # Greek capital Chi
    "\u03a5": "Y",  # Greek capital Upsilon
    "\u0396": "Z",  # Greek capital Zeta
}
HOMOGLYPH_TRANS = str.maketrans(HOMOGLYPH_MAP)


def strip_invisible_and_normalize_whitespace(text: str) -> str:
    """Remove zero-width/bidi spoofing characters and normalize exotic Unicode horizontal spaces to ASCII space."""
    if not text:
        return ""
    cleaned = INVISIBLE_CONTROL_REGEX.sub("", text)
    cleaned = UNICODE_SPACE_REGEX.sub(" ", cleaned)
    return cleaned


def fold_homoglyphs_1to1(text: str) -> str:
    """Fold single-codepoint Cyrillic/Greek/fullwidth confusables 1-to-1 to ASCII without altering string length."""
    if not text:
        return ""
    translated = text.translate(HOMOGLYPH_TRANS)
    # Also fold fullwidth ASCII characters (U+FF01..U+FF5E -> U+0021..U+007E), which are strictly 1-to-1
    out_chars = []
    for ch in translated:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out_chars.append(chr(code - 0xFEE0))
        else:
            out_chars.append(ch)
    return "".join(out_chars)


def normalize_for_security_comparison(text: str) -> str:
    """Normalize untrusted text for leakage and prompt-injection checks (NFKC + strip zero-width + fold homoglyphs)."""
    if not text:
        return ""
    stripped = strip_invisible_and_normalize_whitespace(text)
    folded = fold_homoglyphs_1to1(stripped)
    nfkc = unicodedata.normalize("NFKC", folded)
    nfkc = INVISIBLE_CONTROL_REGEX.sub("", nfkc)
    nfkc = UNICODE_SPACE_REGEX.sub(" ", nfkc)
    return nfkc.casefold()


def atomic_write_text(target_path: Path, content: str, encoding: str = "utf-8") -> None:
    """Atomically write text content to target_path using a temporary file and os.replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp_path.write_text(content, encoding=encoding)
        try:
            tmp_path.replace(target_path)
        except PermissionError:
            target_path.write_text(content, encoding=encoding)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def validate_local_host(host: str) -> None:
    """Ensure backend only runs on localhost to satisfy NFR-001."""
    allowed_hosts = {"127.0.0.1", "localhost"}
    if host not in allowed_hosts:
        raise ValueError(
            f"Security violation: PrivyDoc must bind strictly to localhost ({allowed_hosts}). "
            f"Received: {host}"
        )


def sanitize_filename(filename: str) -> str:
    """Remove path traversal sequences and return safe basename."""
    base = os.path.basename(filename)
    sanitized = "".join(c for c in base if c.isalnum() or c in ("-", "_", "."))
    return sanitized if sanitized else "uploaded_document"


def get_safe_session_dir(document_id: str) -> Path:
    """Validate document_id and return resolved session directory."""
    if not document_id or not document_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document identifier format."
        )
    session_dir = (settings.SESSIONS_DIR / document_id).resolve()
    # Path traversal protection
    if not str(session_dir).startswith(str(settings.SESSIONS_DIR.resolve())):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Illegal directory traversal attempt."
        )
    return session_dir


def validate_file_upload(filename: str, content: bytes) -> str:
    """Validate file extension, size limit, and actual content format/magic bytes.

    Args:
        filename: Uploaded filename.
        content: Raw byte payload.

    Returns:
        Validated file extension ('txt' or 'pdf').

    Raises:
        HTTPException: If file is rejected due to size, invalid extension, or corrupt signature.
    """
    safe_name = sanitize_filename(filename)
    ext = Path(safe_name).suffix.lower()

    # 1. Extension validation
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Only .txt and .pdf files are permitted."
        )

    # 2. File size validation (NFR-007)
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum permitted size of {settings.MAX_UPLOAD_SIZE_MB} MB."
        )

    # 3. Content signature validation (magic bytes)
    if ext == ".pdf":
        # Check first 1024 bytes for standard PDF header
        header = content[:1024]
        if PDF_MAGIC_BYTES not in header:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match standard PDF signature (%PDF-)."
            )
    elif ext == ".txt":
        # Check for binary null bytes
        if b"\x00" in content[:4096]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text file appears to contain binary data (null bytes detected)."
            )

    return ext.lstrip(".")


def cleanup_session(document_id: str) -> bool:
    """Safely delete ephemeral session directory for a document.

    Args:
        document_id: Session identifier.

    Returns:
        True if directory was deleted or did not exist, False on failure.
    """
    try:
        session_dir = get_safe_session_dir(document_id)
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
        return True
    except Exception:
        return False


def cleanup_expired_sessions(max_age_hours: int = 24) -> int:
    """Purge temporary session directories and associated DB records older than max_age_hours.

    Returns:
        Count of purged session directories.
    """
    from app.database.session import delete_document_record, purge_expired_encrypted_aliases

    try:
        purge_expired_encrypted_aliases()
    except Exception:
        pass

    if not settings.SESSIONS_DIR.exists():
        return 0

    now = time.time()
    max_age_seconds = max_age_hours * 3600
    cleaned = 0

    for item in settings.SESSIONS_DIR.iterdir():
        if item.is_dir():
            try:
                mtime = item.stat().st_mtime
                if (now - mtime) > max_age_seconds:
                    doc_id = item.name
                    shutil.rmtree(item, ignore_errors=True)
                    try:
                        delete_document_record(doc_id)
                    except Exception:
                        pass
                    cleaned += 1
            except Exception:
                continue

    return cleaned
