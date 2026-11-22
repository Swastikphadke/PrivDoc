"""Health and status schemas."""

from datetime import datetime, timezone
from typing import List
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., description="Service status", json_schema_extra={"example": "healthy"})
    app_name: str = Field(..., json_schema_extra={"example": "PrivyDoc"})
    version: str = Field(..., json_schema_extra={"example": "0.1.0"})
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    database_connected: bool = Field(..., description="SQLite connection status")
    local_privacy_mode: bool = Field(
        True,
        description="True indicates all processing is restricted to localhost"
    )
    allowed_origins: List[str] = Field(default_factory=list)
