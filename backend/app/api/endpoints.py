"""API router for PrivyDoc endpoints.

Provides health checks, document ingestion, session lifecycle, and coordinate endpoints.
Strictly adheres to local-first privacy (NFR-001) and storage separation (TDR-009).
"""

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from app.core.config import settings
from app.core.security import (
    cleanup_session,
    get_safe_session_dir,
    sanitize_filename,
    validate_file_upload,
)

logger = logging.getLogger(__name__)
DOC_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def _validate_doc_id(document_id: str) -> None:
    """Validate document_id at API boundary before any database or filesystem access."""
    if not document_id or not DOC_ID_PATTERN.match(document_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format.",
        )
from app.database.session import (
    check_db_health,
    delete_document_record,
    get_document_metadata,
    list_all_documents,
    save_document_metadata,
)
from app.processors.pdf_processor import PDFProcessor
from app.processors.txt_processor import TXTProcessor
from app.schemas.candidate import Candidate, DetectionResponse
from app.schemas.entity import EntityGroupResponse, EntityLinkAction, EntityLinkRequest
from app.detectors.entity_resolver import EntityResolver
from app.services.detection_service import DetectionService
from app.schemas.review import (
    ManualCandidateRequest,
    ReviewActionRequest,
    ReviewSummaryResponse,
)
from app.services.review_service import ReviewService
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
        logger.error("Internal parser error while extracting '%s': %s", clean_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal parser error while extracting '{clean_name}'."
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
    "/documents",
    tags=["Documents"],
)
def get_documents_overview() -> Dict[str, Any]:
    """Return real, data-minimized operational telemetry and recent session list for the Dashboard.

    Privacy Invariant:
    Exposes strictly metadata counts, workflow states, and category distributions.
    Never exposes raw document text or sensitive candidate values.
    """
    docs = list_all_documents(limit=25)
    category_distribution: Dict[str, int] = {
        "PERSON": 0,
        "EMAIL": 0,
        "PHONE": 0,
        "ADDRESS": 0,
        "ID_LIKE": 0,
    }
    awaiting_review_count = 0
    verified_exports_count = 0
    suppressed_summaries_count = 0
    total_candidates_detected = 0
    recent_documents: List[Dict[str, Any]] = []

    for d in docs:
        doc_id = d["id"]
        status_val = d.get("status", "PROCESSED")
        cand_total = 0
        approved_cnt = 0
        rejected_cnt = 0
        pending_cnt = 0
        entity_cnt = 0
        export_state = None
        summary_state = None

        try:
            s_dir = get_safe_session_dir(doc_id)
            cands_path = s_dir / "candidates.json"
            if cands_path.exists():
                raw_cands = json.loads(cands_path.read_text(encoding="utf-8"))
                cand_total = len(raw_cands)
                total_candidates_detected += cand_total
                for c in raw_cands:
                    ctype = c.get("type", "DEFAULT")
                    category_distribution[ctype] = category_distribution.get(ctype, 0) + 1
                    rstat = c.get("review_status", "PENDING")
                    if rstat == "APPROVED":
                        approved_cnt += 1
                    elif rstat == "REJECTED":
                        rejected_cnt += 1
                    else:
                        pending_cnt += 1

            ents_path = s_dir / "entities.json"
            if ents_path.exists():
                raw_ents = json.loads(ents_path.read_text(encoding="utf-8"))
                entity_cnt = len(raw_ents)

            exp_path = s_dir / "export_metadata.json"
            if exp_path.exists():
                exp_meta = json.loads(exp_path.read_text(encoding="utf-8"))
                raw_exp_state = exp_meta.get("export_state")
                has_export_file = (s_dir / "sanitized.pdf").exists() or (s_dir / "sanitized.txt").exists()
                if raw_exp_state == "VERIFIED" and has_export_file:
                    export_state = "VERIFIED"
                elif raw_exp_state:
                    export_state = raw_exp_state

            sum_path = s_dir / "summary.json"
            if sum_path.exists():
                sum_meta = json.loads(sum_path.read_text(encoding="utf-8"))
                summary_state = sum_meta.get("state")
        except Exception:
            pass

        if export_state == "VERIFIED":
            verified_exports_count += 1
        if summary_state == "SUPPRESSED":
            suppressed_summaries_count += 1
        if pending_cnt > 0 or status_val in ("PROCESSED", "REVIEWING", "EXTRACTED"):
            if export_state != "VERIFIED":
                awaiting_review_count += 1

        recent_documents.append(
            {
                "document_id": doc_id,
                "filename": d.get("original_filename", doc_id),
                "file_type": d.get("file_type", "txt"),
                "status": status_val,
                "page_count": d.get("page_count", 1),
                "text_length": d.get("text_length", 0),
                "created_at": d.get("created_at"),
                "candidate_count": cand_total,
                "approved_count": approved_cnt,
                "rejected_count": rejected_cnt,
                "pending_count": pending_cnt,
                "entity_count": entity_cnt,
                "export_state": export_state,
                "summary_state": summary_state,
            }
        )

    return {
        "total_documents": len(docs),
        "awaiting_review_count": awaiting_review_count,
        "verified_exports_count": verified_exports_count,
        "suppressed_summaries_count": suppressed_summaries_count,
        "total_candidates_detected": total_candidates_detected,
        "category_distribution": category_distribution,
        "recent_documents": recent_documents,
    }


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    tags=["Documents"],
)
def get_document(document_id: str) -> DocumentResponse:
    """Retrieve document metadata and canonical extracted text for an active session."""
    _validate_doc_id(document_id)
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
    _validate_doc_id(document_id)
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
    _validate_doc_id(document_id)
    # Always purge any ephemeral session directory on disk even if DB record was already removed
    cleanup_session(document_id)
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    # Delete database record and cascade feedback/decisions/aliases
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
    _validate_doc_id(document_id)
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
        logger.error("Detection execution failed for %s: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Detection execution failed due to an internal processing error."
        ) from exc


@router.get(
    "/documents/{document_id}/candidates",
    response_model=List[Candidate],
    tags=["Detection"],
)
def get_candidates(document_id: str) -> List[Candidate]:
    """Retrieve all detected PII candidate spans for human review."""
    _validate_doc_id(document_id)
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
        try:
            det_result = DetectionService.run_detection(document_id)
            return det_result.candidates
        except FileNotFoundError as fnf:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(fnf),
            ) from fnf

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
    _validate_doc_id(document_id)
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
    _validate_doc_id(document_id)
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
    _validate_doc_id(document_id)
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
        logger.error("Entity link operation failed for %s: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Entity link operation failed due to an internal processing error."
        ) from exc


# =========================================================================
# Phase P4: Human Review & Document Workspace Endpoints
# =========================================================================

@router.post(
    "/documents/{document_id}/review",
    response_model=ReviewSummaryResponse,
    tags=["Review"],
)
def submit_review_decision(
    document_id: str,
    payload: ReviewActionRequest,
) -> ReviewSummaryResponse:
    """Submit a human review decision (APPROVE, REJECT, PENDING/UNDO)."""
    _validate_doc_id(document_id)
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    try:
        return ReviewService.submit_review(document_id, payload)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        ) from ve
    except Exception as exc:
        logger.error("Review decision submission failed for %s: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Review decision submission failed due to an internal processing error."
        ) from exc


@router.get(
    "/documents/{document_id}/review",
    response_model=ReviewSummaryResponse,
    tags=["Review"],
)
def get_review_summary(document_id: str) -> ReviewSummaryResponse:
    """Retrieve current review summary statistics and candidate list."""
    _validate_doc_id(document_id)
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    return ReviewService.get_review_summary(document_id)


@router.post(
    "/documents/{document_id}/candidates/manual",
    response_model=Candidate,
    status_code=status.HTTP_201_CREATED,
    tags=["Review"],
)
def add_manual_candidate(
    document_id: str,
    payload: ManualCandidateRequest,
) -> Candidate:
    """Add a user-selected text span as a manual redaction candidate."""
    _validate_doc_id(document_id)
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    try:
        return ReviewService.add_manual_candidate(document_id, payload)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        ) from ve
    except Exception as exc:
        logger.error("Failed to add manual candidate for %s: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add manual candidate due to an internal processing error."
        ) from exc


@router.get(
    "/documents/{document_id}/pages/{page_number}/render",
    tags=["Documents"],
)
def render_pdf_page(document_id: str, page_number: int) -> Response:
    """Render a PDF page to a PNG image stream for UI visual overlay."""
    _validate_doc_id(document_id)
    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    if meta["file_type"] != "pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page image rendering is only supported for PDF documents."
        )

    session_dir = get_safe_session_dir(document_id)
    pdf_path = session_dir / "original.pdf"
    if not pdf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Original PDF file not found."
        )

    import fitz
    doc = None
    try:
        doc = fitz.open(str(pdf_path))
        page_count = doc.page_count
        if page_number < 1 or page_number > page_count:
            raise ValueError(f"Page number {page_number} out of range [1, {page_count}].")

        page = doc[page_number - 1]
        pix = page.get_pixmap(dpi=150)
        png_bytes = pix.tobytes("png")
        return Response(content=png_bytes, media_type="image/png")
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        ) from ve
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to render page %d for %s: %s", page_number, document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to render page {page_number} due to an internal error."
        ) from exc
    finally:
        if doc is not None and not doc.is_closed:
            doc.close()


# =========================================================================
# Phase P5: Redaction & Export Endpoints
# =========================================================================

from fastapi.responses import FileResponse
from app.schemas.redaction import RedactionRequest, RedactionResponse, ExportState
from app.services.redaction_service import RedactionService
import re


@router.post(
    "/documents/{document_id}/redact",
    response_model=RedactionResponse,
    tags=["Redaction & Export"],
)
def execute_redaction(
    document_id: str,
    request: Optional[RedactionRequest] = None,
) -> RedactionResponse:
    """Execute document redaction (TXT and native PyMuPDF PDF) and post-export verification."""
    if not re.match(r"^[a-zA-Z0-9_\-]+$", document_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format."
        )

    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    try:
        response = RedactionService.redact_document(document_id, request)
        return response
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf),
        ) from fnf
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        ) from ve
    except Exception as exc:
        logger.error("Redaction execution failed for %s: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Redaction execution failed due to an internal processing error."
        ) from exc


@router.post(
    "/documents/{document_id}/reconstruct-pdf",
    response_model=RedactionResponse,
    tags=["Redaction & Export"],
)
def reconstruct_pdf_export(
    document_id: str,
    request: Optional[RedactionRequest] = None,
) -> RedactionResponse:
    """Explicitly reconstruct a clean-text PDF alternative from sanitized text (DEC-004).
    
    Security Guarantee:
    Reconstruction must never be triggered automatically when native PDF redaction verification fails.
    It must be an explicit, user-selected action. The reconstructed output is subjected to the full
    independent verification audit and only promoted to VERIFIED after passing all checks.
    """
    _validate_doc_id(document_id)

    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    if meta["file_type"] != "pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clean-text PDF reconstruction is only applicable to PDF documents."
        )

    req = request or RedactionRequest()
    req.force_text_reconstruction = True

    try:
        response = RedactionService.redact_document(document_id, req)
        return response
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf),
        ) from fnf
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        ) from ve
    except Exception as exc:
        logger.error("Clean-text PDF reconstruction failed for %s: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clean-text PDF reconstruction failed due to an internal processing error."
        ) from exc


@router.get(
    "/documents/{document_id}/export/status",
    response_model=RedactionResponse,
    tags=["Redaction & Export"],
)
def get_export_status(document_id: str) -> RedactionResponse:
    """Retrieve post-export verification report and export status."""
    if not re.match(r"^[a-zA-Z0-9_\-]+$", document_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format."
        )

    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    session_dir = get_safe_session_dir(document_id)
    meta_path = session_dir / "export_metadata.json"
    if not meta_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No export has been generated yet for document session '{document_id}'."
        )

    data = json.loads(meta_path.read_text(encoding="utf-8"))
    return RedactionResponse(**data)


@router.get(
    "/documents/{document_id}/export",
    tags=["Redaction & Export"],
)
def download_exported_document(document_id: str, format: Optional[str] = None):
    """Download verified sanitized output document.
    
    Security Guarantee (FR-019, FR-020, NFR-012):
    Only documents that successfully passed 100% of export verification checks
    (status == VERIFIED) can be downloaded. Unverified or failed outputs are strictly blocked.
    Supports optional `format` query parameter ('txt' or 'pdf').
    """
    if not re.match(r"^[a-zA-Z0-9_\-]+$", document_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format."
        )

    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found."
        )

    session_dir = get_safe_session_dir(document_id)
    meta_path = session_dir / "export_metadata.json"
    if not meta_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has not been redacted or exported yet. Call POST /api/documents/{id}/redact first."
        )

    export_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    export_state = export_meta.get("export_state")

    # Double-check: both SQLite status and export_metadata must be VERIFIED
    if export_state != ExportState.VERIFIED.value or meta.get("status") != ExportState.VERIFIED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Export download blocked: document has not passed verification "
                f"(current state: '{export_state}'). Only VERIFIED exports can be downloaded."
            )
        )

    file_type = meta["file_type"]
    requested_format = (format or file_type).lower().strip()
    if requested_format not in ("txt", "pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported export format '{requested_format}'. Allowed: 'txt', 'pdf'."
        )
    if requested_format == "pdf" and file_type != "pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF export is only supported for PDF source documents."
        )

    if requested_format == "pdf":
        export_file_path = session_dir / "sanitized.pdf"
        media_type = "application/pdf"
        download_name = f"sanitized_{meta['original_filename']}"
    else:
        export_file_path = session_dir / "sanitized.txt"
        media_type = "text/plain; charset=utf-8"
        base_stem = meta["original_filename"].rsplit(".", 1)[0]
        download_name = f"sanitized_{base_stem}.txt"

    if not export_file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sanitized file not found on server."
        )

    resolved_file = export_file_path.resolve()
    if resolved_file.parent != session_dir.resolve():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: path traversal attempt detected."
        )

    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    }
    return FileResponse(
        path=export_file_path,
        filename=download_name,
        media_type=media_type,
        headers=headers,
    )


# =========================================================================
# Phase P6: Privacy-Preserving Summarization Endpoints
# =========================================================================

from app.schemas.summary import (
    SanitizedDocument,
    SummaryRequest,
    SummaryResponse,
    SummaryState,
)
from app.services.summary_service import SummaryService


@router.post(
    "/documents/{document_id}/summary",
    response_model=SummaryResponse,
    tags=["Summarization"],
)
def generate_document_summary(
    document_id: str,
    request: Optional[SummaryRequest] = None,
) -> SummaryResponse:
    """Generate, verify, and store a privacy-preserving summary of a verified sanitized document.
    
    Security & Isolation Guarantees (TDR-010, FR-021, NFR-012):
    1. Rejects any document whose export state is not P5 VERIFIED.
    2. Enforces input boundary: summarizer receives ONLY typed SanitizedDocument containing
       verified sanitized text (with category/generic placeholders).
    3. The summarizer and SLM prompt have zero access to raw unredacted text, original files,
       original coordinates, or candidate objects.
    4. Approved sensitive strings are passed exclusively to SummaryGuard for leakage detection.
    5. Fails closed: unsafe outputs are SUPPRESSED from normal display.
    """
    if not re.match(r"^[a-zA-Z0-9_\-]+$", document_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format.",
        )

    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found.",
        )

    session_dir = get_safe_session_dir(document_id)
    export_meta_path = session_dir / "export_metadata.json"
    if not export_meta_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Summarization requires a verified sanitized export. Please complete review and export verification first.",
        )

    try:
        export_meta = json.loads(export_meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Corrupted export metadata on server.",
        )

    # Gate: Only P5 VERIFIED exports may enter summarization
    export_state = export_meta.get("export_state")
    if export_state != ExportState.VERIFIED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Summarization blocked: document export state is '{export_state}'. "
                "Only P5 VERIFIED sanitized exports may be summarized."
            ),
        )

    sanitized_txt_path = session_dir / "sanitized.txt"
    if not sanitized_txt_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sanitized document text missing from session directory.",
        )

    sanitized_text = sanitized_txt_path.read_text(encoding="utf-8")
    if not sanitized_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sanitized text is empty; cannot generate summary.",
        )

    # Construct strict SanitizedDocument contract
    verif_ref = export_meta.get("verification", {}).get("verified_at") or "P5-VERIFIED"
    sanitized_doc = SanitizedDocument(
        document_id=document_id,
        sanitized_text=sanitized_text,
        export_verification_ref=str(verif_ref),
        document_format=meta["file_type"],
        permitted_metadata={
            "page_count": meta.get("page_count", 1),
            "text_length": len(sanitized_text),
        },
    )

    # Prepare reference data STRICTLY for SummaryGuard leakage detection
    candidates = EntityResolver.load_candidates(document_id)
    entities = EntityResolver.load_entities(document_id)
    approved_vals = [c.text for c in candidates if c.review_status == "APPROVED"]
    approved_cand_ids = {c.candidate_id for c in candidates if c.review_status == "APPROVED"}
    entity_variants = [
        v for ent in entities
        if any(cid in approved_cand_ids for cid in ent.candidate_ids)
        for v in ent.variants
    ]
    guard_references = {
        "approved_values": approved_vals,
        "entity_variants": entity_variants,
    }

    if request is None:
        request = SummaryRequest()

    try:
        response = SummaryService.generate_summary(
            sanitized_doc=sanitized_doc,
            request=request,
            guard_references=guard_references,
        )
        return response
    except Exception as exc:
        logger.error("Failed to generate summary for document %s: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating or verifying the document summary.",
        )


@router.get(
    "/documents/{document_id}/summary",
    response_model=SummaryResponse,
    tags=["Summarization"],
)
def get_document_summary(document_id: str) -> SummaryResponse:
    """Retrieve existing verified summary and verification audit report."""
    if not re.match(r"^[a-zA-Z0-9_\-]+$", document_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format.",
        )

    meta = get_document_metadata(document_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document session '{document_id}' not found.",
        )

    summary = SummaryService.get_existing_summary(document_id)
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No summary has been generated yet for document session '{document_id}'.",
        )

    return summary


# =========================================================================
# Phase P7: Local Privacy-Preserving Feedback & Opt-In Alias Endpoints
# =========================================================================

from app.schemas.feedback import (
    FeedbackAnalysisReport,
    FeedbackRecordSchema,
    OptInAliasRequest,
)
from app.services.feedback_service import FeedbackService
from app.database.session import get_feedback_records


@router.get(
    "/feedback/analysis",
    response_model=FeedbackAnalysisReport,
    tags=["Feedback & Evaluation"],
)
def get_feedback_analysis(document_id: Optional[str] = None) -> FeedbackAnalysisReport:
    """Analyze aggregated user feedback and generate structured rule modification proposals.
    
    Security Guarantee:
    Does NOT mutate detection patterns or fine-tune models automatically.
    Produces proposals requiring explicit human developer review.
    """
    if document_id is not None:
        _validate_doc_id(document_id)
    return FeedbackService.analyze_feedback(document_id=document_id)


@router.get(
    "/documents/{document_id}/feedback",
    response_model=List[Dict[str, Any]],
    tags=["Feedback & Evaluation"],
)
def get_document_feedback(document_id: str) -> List[Dict[str, Any]]:
    """Retrieve data-minimized feedback event records for a document session.
    
    Data Minimization Guarantee:
    Returns only structural event records (category, action, source, confidence).
    Contains zero raw document text, snippets, or candidate PII.
    """
    _validate_doc_id(document_id)
    return get_feedback_records(doc_id=document_id)


@router.post(
    "/documents/{document_id}/aliases",
    tags=["Feedback & Evaluation"],
)
def store_opt_in_encrypted_alias(
    document_id: str,
    request: OptInAliasRequest,
) -> Dict[str, Any]:
    """Store an encrypted name variant alias with explicit opt-in consent.
    
    Privacy Guarantee:
    Fails with 400 if opt_in_consent is not explicitly True.
    Uses AES-256-GCM encryption with expiration retention.
    """
    _validate_doc_id(document_id)
    if request.document_id != document_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path document_id does not match request body document_id.",
        )

    try:
        rec_id = FeedbackService.store_opt_in_alias(request)
        return {
            "status": "STORED",
            "alias_record_id": rec_id,
            "document_id": document_id,
            "entity_id": request.entity_id,
            "retention_days": request.retention_days,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/documents/{document_id}/aliases",
    tags=["Feedback & Evaluation"],
)
def get_opt_in_aliases(document_id: str) -> List[Dict[str, Any]]:
    """Retrieve decrypted aliases for the active document session."""
    _validate_doc_id(document_id)
    return FeedbackService.get_opt_in_aliases(document_id)


@router.delete(
    "/documents/{document_id}/aliases",
    tags=["Feedback & Evaluation"],
)
def delete_document_aliases(document_id: str) -> Dict[str, Any]:
    """Purge all encrypted aliases associated with a document session."""
    _validate_doc_id(document_id)
    FeedbackService.clear_document_data(document_id)
    return {"status": "DELETED", "document_id": document_id}





