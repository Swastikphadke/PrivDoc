"""SQLite metadata persistence foundation.

Strict Privacy Rule:
Never store raw document contents, canonical extracted text, or PDF coordinates in SQLite.
SQLite is used solely for session metadata, candidate review statuses, and minimal feedback.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from app.core.config import settings


def init_db() -> None:
    """Initialize SQLite tables for session metadata and review decisions."""
    try:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        settings.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    
    with sqlite3.connect(settings.DATABASE_PATH) as conn:
        cursor = conn.cursor()
        
        # Document metadata table (no raw text)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                status TEXT NOT NULL,
                page_count INTEGER DEFAULT 0,
                text_length INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        """)
        
        # Review decisions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS review_decisions (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                scope TEXT DEFAULT 'OCCURRENCE',
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        """)
        
        # Local feedback table migration check
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback_records'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(feedback_records)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            if "document_id" not in existing_cols:
                cursor.execute("DROP TABLE feedback_records")

        # Local feedback table (data-minimized event metrics; NO raw text or PII)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_records (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                candidate_id TEXT,
                entity_id TEXT,
                action TEXT NOT NULL,
                candidate_type TEXT NOT NULL,
                source TEXT,
                confidence REAL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        """)

        # Optional opt-in encrypted aliases table (explicit consent required)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opt_in_encrypted_aliases (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                encrypted_alias BLOB NOT NULL,
                nonce BLOB NOT NULL,
                opt_in_consent INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        """)
        conn.commit()


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Yield a SQLite database connection with row factory enabled."""
    conn = sqlite3.connect(settings.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def check_db_health() -> bool:
    """Verify SQLite database connectivity and integrity."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return cursor.fetchone()[0] == 1
    except Exception:
        return False


def save_document_metadata(
    doc_id: str,
    filename: str,
    file_type: str,
    status: str,
    page_count: int,
    text_length: int
) -> None:
    """Insert or replace document metadata in SQLite."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO documents (id, original_filename, file_type, status, page_count, text_length)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (doc_id, filename, file_type, status, page_count, text_length))
        conn.commit()


def get_document_metadata(doc_id: str) -> dict | None:
    """Retrieve document metadata by document ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def list_all_documents(limit: int = 25) -> list[dict]:
    """List recent document metadata records ordered by creation time descending (zero raw PII)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM documents ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_document_record(doc_id: str) -> bool:
    """Remove document metadata record and associated feedback/decisions from SQLite."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("DELETE FROM review_decisions WHERE document_id = ?", (doc_id,))
        cursor.execute("DELETE FROM feedback_records WHERE document_id = ?", (doc_id,))
        cursor.execute("DELETE FROM opt_in_encrypted_aliases WHERE document_id = ?", (doc_id,))
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        return cursor.rowcount > 0


def update_document_status(doc_id: str, new_status: str) -> bool:
    """Update processing or export status for a document session."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE documents SET status = ? WHERE id = ?", (new_status, doc_id))
        conn.commit()
        return cursor.rowcount > 0


def record_review_decision(
    doc_id: str,
    cand_id: str,
    decision: str,
    scope: str = "OCCURRENCE"
) -> None:
    """Record or update a human review decision in SQLite."""
    import uuid
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Delete prior decision for this candidate if any
        cursor.execute(
            "DELETE FROM review_decisions WHERE document_id = ? AND candidate_id = ?",
            (doc_id, cand_id)
        )
        cursor.execute("""
            INSERT INTO review_decisions (id, document_id, candidate_id, decision, scope)
            VALUES (?, ?, ?, ?, ?)
        """, (f"rev_{uuid.uuid4().hex[:12]}", doc_id, cand_id, decision, scope))
        conn.commit()


def get_document_review_decisions(doc_id: str) -> list[dict]:
    """Retrieve all review decisions for a document session."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM review_decisions WHERE document_id = ? ORDER BY reviewed_at ASC",
            (doc_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Phase P7: Local Feedback & Opt-In Alias Persistence (Data-Minimized)
# =============================================================================

def record_feedback_event(
    doc_id: str,
    candidate_type: str,
    action: str,
    candidate_id: str | None = None,
    entity_id: str | None = None,
    source: str | None = None,
    confidence: float | None = None,
    details: str | None = None,
) -> str:
    """Record a data-minimized feedback event in SQLite.
    
    Strict Privacy Invariant:
    Never passes or stores raw document text, snippets, or raw candidate strings.
    `details` must contain only non-PII operational metadata (e.g. JSON with counts,
    scope, or categorical changes).
    """
    import uuid
    fb_id = f"fb_{uuid.uuid4().hex[:12]}"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedback_records (
                id, document_id, candidate_id, entity_id, action,
                candidate_type, source, confidence, details
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fb_id, doc_id, candidate_id, entity_id, action,
            candidate_type, source, confidence, details
        ))
        conn.commit()
    return fb_id


def get_feedback_records(
    doc_id: str | None = None,
    action: str | None = None,
    candidate_type: str | None = None,
) -> list[dict]:
    """Query data-minimized feedback event records."""
    query = "SELECT * FROM feedback_records WHERE 1=1"
    params: list = []
    if doc_id:
        query += " AND document_id = ?"
        params.append(doc_id)
    if action:
        query += " AND action = ?"
        params.append(action)
    if candidate_type:
        query += " AND candidate_type = ?"
        params.append(candidate_type)
    query += " ORDER BY created_at ASC"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]


def delete_feedback_records(doc_id: str) -> int:
    """Remove feedback records for a specific document session."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM feedback_records WHERE document_id = ?", (doc_id,))
        conn.commit()
        return cursor.rowcount


def record_opt_in_encrypted_alias(
    doc_id: str,
    entity_id: str,
    encrypted_alias: bytes,
    nonce: bytes,
    expires_at: str | None = None,
) -> str:
    """Store an encrypted alias record requiring explicit opt-in consent."""
    import uuid
    rec_id = f"enc_alias_{uuid.uuid4().hex[:12]}"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO opt_in_encrypted_aliases (
                id, document_id, entity_id, encrypted_alias, nonce, opt_in_consent, expires_at
            )
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (rec_id, doc_id, entity_id, encrypted_alias, nonce, expires_at))
        conn.commit()
    return rec_id


def get_opt_in_encrypted_aliases(doc_id: str) -> list[dict]:
    """Retrieve encrypted aliases for a document session."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM opt_in_encrypted_aliases WHERE document_id = ?",
            (doc_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_encrypted_aliases(doc_id: str) -> int:
    """Delete all encrypted aliases associated with a document session."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM opt_in_encrypted_aliases WHERE document_id = ?", (doc_id,))
        conn.commit()
        return cursor.rowcount


def purge_expired_encrypted_aliases() -> int:
    """Purge expired encrypted alias records based on retention policy."""
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    now_sql = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM opt_in_encrypted_aliases WHERE expires_at IS NOT NULL AND (expires_at < ? OR expires_at < ?)",
            (now_iso, now_sql),
        )
        conn.commit()
        return cursor.rowcount

