"""PrivyDoc FastAPI Application Entry Point.

Ensures strict local-first privacy, CORS restrictions, and modular foundation.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import router as api_router
from app.core.config import settings
from app.core.security import cleanup_expired_sessions, validate_local_host
from app.database.session import init_db
from app.schemas.health import HealthResponse
from app.database.session import check_db_health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle startup and shutdown hooks."""
    # Ensure localhost binding configuration
    validate_local_host(settings.HOST)
    # Initialize SQLite database and directory structures
    init_db()
    # Purge expired sessions and expired encrypted aliases on startup
    cleanup_expired_sessions(settings.SESSION_TTL_HOURS)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Privacy-Aware Document Redaction and Summary Tool (Local-first)",
    lifespan=lifespan,
)

# Enforce strict local-only CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Mount API endpoints
app.include_router(api_router, prefix="/api")

# Also mount root /health directly as specified in FR/task requirements
@app.get("/health", response_model=HealthResponse, tags=["System"])
def direct_health() -> HealthResponse:
    """Direct root health endpoint."""
    db_ok = check_db_health()
    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        database_connected=db_ok,
        local_privacy_mode=True,
        allowed_origins=settings.ALLOWED_ORIGINS,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
