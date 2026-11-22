"""API router for PrivyDoc foundation endpoints."""

from fastapi import APIRouter
from app.core.config import settings
from app.database.session import check_db_health
from app.schemas.health import HealthResponse


router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
def get_health() -> HealthResponse:
    """Return health status, database connection, and local privacy configuration."""
    db_ok = check_db_health()
    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        database_connected=db_ok,
        local_privacy_mode=True,
        allowed_origins=settings.ALLOWED_ORIGINS,
    )


@router.get("/", tags=["System"])
def root_status() -> dict:
    """Root endpoint providing product identity and local status."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "mode": "local-first privacy-preserving",
        "docs_url": "/docs" if settings.DEBUG else "disabled in production",
        "health_check": "/api/health",
    }
