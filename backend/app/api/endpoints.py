"""API router for PrivyDoc endpoints.

Provides health checks, document ingestion, session lifecycle, and coordinate endpoints.
Strictly adheres to local-first privacy (NFR-001) and storage separation (TDR-009).
"""

import json
import uuid
from typing import List
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from app.core.config import settings
from app.core.security import (
    cleanup_session,
    get_safe_session_dir,
    sanitize_filename,
    validate_file_upload,
)
from app.database.session import (
    check_db_health,
    delete_document_record,
    get_document_metadata,
    save_document_metadata,
)
from app.processors.pdf_processor import PDFProcessor
from app.processors.txt_processor import TXTProcessor
from app.schemas.candidate import Candidate, DetectionResponse
from app.schemas.entity import EntityGroupResponse, EntityLinkAction, EntityLinkRequest
from app.detectors.entity_resolver import EntityResolver
from app.services.detection_service import DetectionService
from app.schemas.document import (
    CoordinateSpan,
    DocumentCoordinatesResponse,
    DocumentResponse,
)
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


# =========================================================================
# Phase P1: Document Ingestion & Extraction Endpoints
# =========================================================================

@router.post(
    "/documents/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Documents"],
)
async def upload_document(file: UploadFile = File(...)) -> DocumentResponse:
    """Ingest a TXT or text-based PDF document.

    Validates file format, size, and magic bytes. Extracts canonical text
    and coordinate mappings into an ephemeral local session folder.
    Metadata is recorded in SQLite.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename."
        )

    # 1. Read byte stream
    content = await file.read()

    # 2. Security & format validation (magic bytes, size, extension)
    file_type = validate_file_upload(file.filename, content)
    clean_name = sanitize_filename(file.filename)

    # 3. Generate session ID and create ephemeral session directory
    document_id = uuid.uuid4().hex
    session_dir = get_safe_session_dir(document_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    canonical_text: str = ""
    page_count: int = 1
    coordinates: List[CoordinateSpan] = []
    warnings: List[str] = []

    # 4. Process document according to validated type
    try:
        if file_type == "txt":
            canonical_text, warnings = TXTProcessor.extract(content, clean_name)
            page_count = 1
        elif file_type == "pdf":
            canonical_text, page_count, coordinates, warnings = PDFProcessor.extract(
                content, clean_name
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type '{file_type}'."
            )
    except ValueError as val_err:
        # Cleanup temporary session on parsing failure
        cleanup_session(document_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err)
        ) from val_err
    except Exception as exc:
        cleanup_session(document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal parser error while extracting '{clean_name}': {str(exc)}"
        ) from exc

    # 5. Store session artifacts locally (ephemeral storage)
    original_path = session_dir / f"original.{file_type}"
    original_path.write_bytes(content)

    canonical_path = session_dir / "canonical.txt"
    canonical_path.write_text(canonical_text, encoding="utf-8")

    if coordinates:
        coords_path = session_dir / "coordinates.json"
        coords_data = [c.model_dump() for c in coordinates]
        coords_path.write_text(json.dumps(coords_data), encoding="utf-8")

    # 6. Save metadata to SQLite (zero raw text in DB)
    text_length = len(canonical_text)
    save_document_metadata(
        doc_id=document_id,
        filename=clean_name,
        file_type=file_type,
        status="PROCESSED",
        page_count=page_count,
        text_length=text_length,
    )

    return DocumentResponse(
        document_id=document_id,
        filename=clean_name,
        file_type=file_type,
        status="PROCESSED",
        page_count=page_count,
        text_length=text_length,
        extracted_text=canonical_text,
        warnings=warnings,
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    tags=["Documents"],
)
def get_document(document_id: str) -> DocumentResponse:
    """Retrieve document metadata and canonical extracted text for an active session."""
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    session_dir = get_safe_session_dir(document_id)
    canonical_path = session_dir / "canonical.txt"

    if not canonical_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Canonical text file for session '{document_id}' has expired or was deleted."
        )

    extracted_text = canonical_path.read_text(encoding="utf-8")

    return DocumentResponse(
        document_id=meta["id"],
        filename=meta["original_filename"],
        file_type=meta["file_type"],
        status=meta["status"],
        page_count=meta["page_count"],
        text_length=meta["text_length"],
        extracted_text=extracted_text,
        warnings=[],
    )


@router.get(
    "/documents/{document_id}/coordinates",
    response_model=DocumentCoordinatesResponse,
    tags=["Documents"],
)
def get_document_coordinates(document_id: str) -> DocumentCoordinatesResponse:
    """Retrieve PDF word/span coordinate mappings for UI synchronization."""
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    session_dir = get_safe_session_dir(document_id)
    coords_path = session_dir / "coordinates.json"

    coordinates: List[CoordinateSpan] = []
    if coords_path.exists():
        raw_coords = json.loads(coords_path.read_text(encoding="utf-8"))
        coordinates = [CoordinateSpan(**item) for item in raw_coords]

    return DocumentCoordinatesResponse(
        document_id=document_id,
        page_count=meta["page_count"],
        total_spans=len(coordinates),
        coordinates=coordinates,
    )


@router.delete(
    "/documents/{document_id}",
    tags=["Documents"],
)
def delete_document(document_id: str) -> dict:
    """Manually purge an active session, removing all local ephemeral files and metadata."""
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    # 1. Purge ephemeral files
    cleanup_session(document_id)
    # 2. Delete database record
    delete_document_record(document_id)

    return {
        "status": "DELETED",
        "document_id": document_id,
        "detail": "Ephemeral session files and metadata successfully purged."
    }


# =========================================================================
# Phase P2: Hybrid PII Detection Endpoints
# =========================================================================

@router.post(
    "/documents/{document_id}/detect",
    response_model=DetectionResponse,
    tags=["Detection"],
)
def detect_pii(document_id: str) -> DetectionResponse:
    """Execute hybrid detection (Regex + NER) over the canonical text of a document."""
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    try:
        response = DetectionService.run_detection(document_id)
        return response
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf)
        ) from fnf
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Detection execution failed: {str(exc)}"
        ) from exc


@router.get(
    "/documents/{document_id}/candidates",
    response_model=List[Candidate],
    tags=["Detection"],
)
def get_candidates(document_id: str) -> List[Candidate]:
    """Retrieve all detected PII candidate spans for human review."""
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    session_dir = get_safe_session_dir(document_id)
    cands_path = session_dir / "candidates.json"

    if not cands_path.exists():
        # If detection has not been executed yet, trigger it on-demand
        det_result = DetectionService.run_detection(document_id)
        return det_result.candidates

    raw_cands = json.loads(cands_path.read_text(encoding="utf-8"))
    return [Candidate(**c) for c in raw_cands]


# =========================================================================
# Phase P3: Entity Resolution Endpoints
# =========================================================================

@router.post(
    "/documents/{document_id}/entities/resolve",
    response_model=EntityGroupResponse,
    tags=["Entity Resolution"],
)
def resolve_entities(document_id: str) -> EntityGroupResponse:
    """Run multi-stage entity resolution over document candidates."""
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    session_dir = get_safe_session_dir(document_id)
    canonical_path = session_dir / "canonical.txt"
    if not canonical_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canonical text not found for this document session."
        )

    canonical_text = canonical_path.read_text(encoding="utf-8")
    candidates = EntityResolver.load_candidates(document_id)
    if not candidates:
        det_result = DetectionService.run_detection(document_id)
        candidates = det_result.candidates

    return EntityResolver.resolve_entities(
        document_id=document_id,
        candidates=candidates,
        canonical_text=canonical_text,
        use_slm=True,
    )


@router.get(
    "/documents/{document_id}/entities",
    response_model=EntityGroupResponse,
    tags=["Entity Resolution"],
)
def get_entities(document_id: str) -> EntityGroupResponse:
    """Retrieve all resolved entity clusters for a document session."""
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    entities = EntityResolver.load_entities(document_id)
    if not entities:
        # Run resolution if not already computed
        return resolve_entities(document_id)

    return EntityGroupResponse(
        document_id=document_id,
        total_entities=len(entities),
        entities=entities,
        degraded_mode=False,
        slm_available=True,
        warnings=[],
    )


@router.post(
    "/documents/{document_id}/entities/link",
    response_model=EntityGroupResponse,
    tags=["Entity Resolution"],
)
def link_entities(
    document_id: str,
    payload: EntityLinkRequest,
) -> EntityGroupResponse:
    """Manually link or unlink candidate occurrences to/from entity clusters."""
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    try:
        if payload.action == EntityLinkAction.UNLINK:
            return EntityResolver.unlink_candidates(
                document_id=document_id,
                candidate_ids=payload.candidate_ids,
            )
        else:
            return EntityResolver.link_candidates(
                document_id=document_id,
                candidate_ids=payload.candidate_ids,
                target_entity_id=payload.target_entity_id,
            )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        ) from ve
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Entity link operation failed: {str(exc)}"
        ) from exc

