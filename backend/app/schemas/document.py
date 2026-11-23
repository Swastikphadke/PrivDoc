"""Pydantic schemas for Document ingestion, responses, and coordinate mappings."""

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Bounding box coordinates [x0, y0, x1, y1] on a PDF page in points."""
    x0: float
    y0: float
    x1: float
    y1: float


class CoordinateSpan(BaseModel):
    """Mapping between canonical text character offsets and PDF page coordinates."""
    page_number: int = Field(..., description="1-indexed PDF page number")
    bbox: List[float] = Field(..., description="[x0, y0, x1, y1] coordinates in page.rect space")
    char_start: int = Field(..., description="Inclusive start offset in canonical text")
    char_end: int = Field(..., description="Exclusive end offset in canonical text")
    text: str = Field(..., description="The word or span text")
    page_x0: float = Field(default=0.0, description="Page visible rect x0 origin")
    page_y0: float = Field(default=0.0, description="Page visible rect y0 origin")
    page_width: float = Field(default=595.0, description="Page visible rect width in points")
    page_height: float = Field(default=842.0, description="Page visible rect height in points")
    page_rotation: int = Field(default=0, description="Page rotation angle in degrees")


class DocumentResponse(BaseModel):
    """Full document representation returned after ingestion or lookup."""
    document_id: str = Field(..., description="Unique session identifier")
    filename: str = Field(..., description="Sanitized original filename")
    file_type: str = Field(..., description="'txt' or 'pdf'")
    status: str = Field(..., description="Processing status: PROCESSED, REJECTED, FAILED")
    page_count: int = Field(default=1, description="Total number of pages (1 for TXT)")
    text_length: int = Field(..., description="Total character count in canonical text")
    extracted_text: str = Field(..., description="Canonical extracted text with Unicode offsets")
    warnings: List[str] = Field(default_factory=list, description="Extraction warnings or notes")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentSummary(BaseModel):
    """Summary metadata without the full extracted text body."""
    document_id: str
    filename: str
    file_type: str
    status: str
    page_count: int
    text_length: int
    warnings: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentCoordinatesResponse(BaseModel):
    """Positional coordinate mappings for PDF viewer synchronization."""
    document_id: str
    page_count: int
    total_spans: int
    coordinates: List[CoordinateSpan]
