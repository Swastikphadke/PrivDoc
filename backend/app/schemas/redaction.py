"""Pydantic schemas for document redaction, verification, and export.

Strict Privacy Rule:
Verification issues and responses MUST NOT log or expose raw PII values.
All issues refer to candidate IDs, entity IDs, categories, or page numbers.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ExportState(str, Enum):
    """Document export lifecycle state."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNVERIFIED = "UNVERIFIED"


class PlaceholderStyle(str, Enum):
    """Placeholder formatting strategy for redacted spans."""
    CATEGORY = "CATEGORY"  # [PERSON], [EMAIL], [PHONE], etc.
    GENERIC = "GENERIC"    # [REDACTED]
    BLOCK = "BLOCK"        # ████████
    CUSTOM = "CUSTOM"      # Custom user string template


class RedactionRequest(BaseModel):
    """Configuration payload for document redaction execution."""
    placeholder_style: PlaceholderStyle = Field(
        default=PlaceholderStyle.CATEGORY,
        description="Placeholder formatting strategy for redacted spans."
    )
    custom_placeholder: Optional[str] = Field(
        default=None,
        description="Custom template if placeholder_style is CUSTOM (e.g. '[CONFIDENTIAL]')."
    )
    force_text_reconstruction: bool = Field(
        default=False,
        description="Explicit user request to rebuild PDF cleanly from sanitized text (layout fallback)."
    )


class VerificationIssue(BaseModel):
    """Individual issue or violation detected by post-export verification."""
    check_name: str = Field(description="Name of verification rule (e.g. EXACT_MATCH, METADATA_LEAK).")
    description: str = Field(description="Masked description of the issue. NEVER contains raw PII.")
    severity: str = Field(default="ERROR", description="'ERROR' (fails export) or 'WARNING'.")
    page_number: Optional[int] = Field(default=None, description="Page number where issue was detected.")
    candidate_id: Optional[str] = Field(default=None, description="Related candidate ID, if applicable.")


class VerificationResult(BaseModel):
    """Comprehensive post-export verification audit result."""
    status: str = Field(description="'PASSED' or 'FAILED'.")
    checks_run: List[str] = Field(default_factory=list, description="List of verification checks performed.")
    issues: List[VerificationIssue] = Field(default_factory=list, description="List of detected verification issues.")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings or limitations.")
    verified_at: str = Field(description="ISO-8601 timestamp of verification execution.")


class RedactionResponse(BaseModel):
    """API response model for document redaction and export generation."""
    document_id: str
    export_state: ExportState
    file_type: str
    export_filename: str
    approved_redactions_applied: int
    rejected_spans_preserved: int
    unreviewed_spans_preserved: int
    sanitized_text_preview: Optional[str] = None
    verification: VerificationResult
    download_ready: bool
    reconstructed_pdf_used: bool = False
    layout_warning: Optional[str] = None
