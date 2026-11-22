"""Security controls, file validation, and path protections."""

import os
from pathlib import Path
from typing import Set
from fastapi import HTTPException, status
from app.core.config import settings


ALLOWED_EXTENSIONS: Set[str] = {".txt", ".pdf"}


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
    return "".join(c for c in base if c.isalnum() or c in ("-", "_", "."))


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
