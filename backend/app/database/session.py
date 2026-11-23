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
        
        # Local feedback table (anonymized metrics, no raw PII)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_records (
                id TEXT PRIMARY KEY,
                candidate_type TEXT NOT NULL,
                action TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def delete_document_record(doc_id: str) -> bool:
    """Remove document metadata record from SQLite."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
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
