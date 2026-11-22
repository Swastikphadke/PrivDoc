"""Security controls, file validation, and path protections."""

import os
import shutil
import time
from pathlib import Path
from typing import Set
from fastapi import HTTPException, status
from app.core.config import settings


ALLOWED_EXTENSIONS: Set[str] = {".txt", ".pdf"}
PDF_MAGIC_BYTES: bytes = b"%PDF-"


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
    if not document_id or not document_id.replace("-", "").isalnum():
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
    """Purge temporary session directories older than max_age_hours.

    Returns:
        Count of purged session directories.
    """
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
                    shutil.rmtree(item, ignore_errors=True)
                    cleaned += 1
            except Exception:
                continue

    return cleaned
