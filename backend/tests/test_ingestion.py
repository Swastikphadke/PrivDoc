"""Unit and integration tests for Phase P1: Document Ingestion and Extraction.

Validates TXT and PDF parsers, security filters, coordinate mappings,
error handling for malformed/encrypted/scanned documents, and session cleanup.
"""

import io
import pytest
import pymupdf
from fastapi.testclient import TestClient
from app.main import app
from app.processors.txt_processor import TXTProcessor
from app.processors.pdf_processor import PDFProcessor
from app.core.security import validate_file_upload, sanitize_filename
from app.database.session import init_db


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Ensure database tables exist before running ingestion tests."""
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def create_sample_pdf(text: str = "Test document content") -> bytes:
    """Helper to generate a clean, single-page text-based PDF in memory."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def create_multipage_pdf() -> bytes:
    """Helper to generate a 2-page text-based PDF."""
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((50, 72), "Page One: Patient John Doe admitted.")
    p2 = doc.new_page()
    p2.insert_text((50, 72), "Page Two: Contact family at 9876543210.")
    data = doc.tobytes()
    doc.close()
    return data


def create_encrypted_pdf() -> bytes:
    """Helper to generate an AES-encrypted password-protected PDF."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Confidential records.")
    data = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="secret123",
        owner_pw="admin123"
    )
    doc.close()
    return data


def create_image_only_pdf() -> bytes:
    """Helper to generate a PDF containing only an image (no extractable text)."""
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 80), 1)
    pix.clear_with(255)
    page.insert_image(pymupdf.Rect(50, 50, 150, 150), pixmap=pix)
    data = doc.tobytes()
    doc.close()
    return data


# =========================================================================
# Processor Unit Tests
# =========================================================================

def test_txt_processor_valid_utf8():
    """Verify TXT processor extracts text and normalizes newlines."""
    content = "Line 1\r\nLine 2\rLine 3\n".encode("utf-8")
    text, warnings = TXTProcessor.extract(content, "sample.txt")
    assert text == "Line 1\nLine 2\nLine 3\n"
    assert len(warnings) == 0


def test_txt_processor_fallback_encoding():
    """Verify TXT processor uses documented fallback for non-UTF8 text."""
    # Latin-1 specific string
    latin1_bytes = "Café au lait and résumé".encode("latin-1")
    text, warnings = TXTProcessor.extract(latin1_bytes, "french.txt")
    assert "Café" in text
    assert len(warnings) == 1
    assert "latin-1" in warnings[0].lower()


def test_txt_processor_empty_file():
    """Verify TXT processor rejects 0-byte or whitespace-only files."""
    with pytest.raises(ValueError) as exc1:
        TXTProcessor.extract(b"", "empty.txt")
    assert "empty" in str(exc1.value).lower()

    with pytest.raises(ValueError) as exc2:
        TXTProcessor.extract(b"   \n\t  \n", "whitespace.txt")
    assert "whitespace only" in str(exc2.value).lower()


def test_pdf_processor_valid_text():
    """Verify PDF processor extracts text and coordinates."""
    pdf_bytes = create_sample_pdf("Richa Sharma lives in Delhi.")
    text, page_count, coords, warnings = PDFProcessor.extract(pdf_bytes, "report.pdf")
    assert page_count == 1
    assert "Richa Sharma" in text
    assert len(coords) > 0
    # Verify word coordinates exist and match canonical offsets
    first_coord = coords[0]
    assert first_coord.text == "Richa"
    assert text[first_coord.char_start:first_coord.char_end] == "Richa"
    assert len(first_coord.bbox) == 4


def test_pdf_processor_multipage():
    """Verify multi-page PDF extracts correct page count and delimiter."""
    pdf_bytes = create_multipage_pdf()
    text, page_count, coords, warnings = PDFProcessor.extract(pdf_bytes, "multi.pdf")
    assert page_count == 2
    assert "Page One" in text
    assert "Page Two" in text
    # Verify coordinates span across both pages
    pages_in_coords = {c.page_number for c in coords}
    assert 1 in pages_in_coords
    assert 2 in pages_in_coords


def test_pdf_processor_encrypted():
    """Verify encrypted PDF is detected and rejected with clear error."""
    enc_bytes = create_encrypted_pdf()
    with pytest.raises(ValueError) as exc:
        PDFProcessor.extract(enc_bytes, "locked.pdf")
    assert "password-protected" in str(exc.value).lower() or "encrypted" in str(exc.value).lower()


def test_pdf_processor_image_only():
    """Verify scanned/image-only PDF is rejected as out of scope."""
    img_bytes = create_image_only_pdf()
    with pytest.raises(ValueError) as exc:
        PDFProcessor.extract(img_bytes, "scan.pdf")
    assert "image-only" in str(exc.value).lower() or "scanned" in str(exc.value).lower()


def test_pdf_processor_malformed():
    """Verify corrupt PDF byte sequence raises clean ValueError."""
    corrupt_bytes = b"%PDF-1.4\nInvalid binary data and header trailer not found"
    with pytest.raises(ValueError) as exc:
        PDFProcessor.extract(corrupt_bytes, "corrupted.pdf")
    assert "malformed" in str(exc.value).lower() or "corrupted" in str(exc.value).lower()


# =========================================================================
# API Integration Tests (Upload, Fetch, Delete)
# =========================================================================

def test_api_upload_valid_txt(client):
    """Test POST /api/documents/upload with valid TXT file."""
    txt_content = "Patient: Priya Nair\nAge: 32\nCity: Chennai\n"
    response = client.post(
        "/api/documents/upload",
        files={"file": ("medical_note.txt", txt_content.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["file_type"] == "txt"
    assert data["status"] == "PROCESSED"
    assert data["page_count"] == 1
    assert data["text_length"] == len(txt_content)
    assert "Priya Nair" in data["extracted_text"]
    assert "document_id" in data

    doc_id = data["document_id"]

    # Verify GET /api/documents/{id}
    get_resp = client.get(f"/api/documents/{doc_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["document_id"] == doc_id
    assert get_resp.json()["extracted_text"] == txt_content

    # Clean up
    del_resp = client.delete(f"/api/documents/{doc_id}")
    assert del_resp.status_code == 200


def test_api_upload_valid_pdf(client):
    """Test POST /api/documents/upload with valid PDF file and coordinate retrieval."""
    pdf_bytes = create_sample_pdf("Account holder: Rahul Verma, ID: ACC-99201")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("statement.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["file_type"] == "pdf"
    assert data["page_count"] == 1
    assert "Rahul Verma" in data["extracted_text"]

    doc_id = data["document_id"]

    # Verify GET /api/documents/{id}/coordinates
    coords_resp = client.get(f"/api/documents/{doc_id}/coordinates")
    assert coords_resp.status_code == 200
    coords_data = coords_resp.json()
    assert coords_data["page_count"] == 1
    assert coords_data["total_spans"] > 0
    assert len(coords_data["coordinates"]) > 0

    # Clean up
    client.delete(f"/api/documents/{doc_id}")


def test_api_upload_unicode_content(client):
    """Test ingestion with non-ASCII Unicode characters (Hindi, accents, symbols)."""
    unicode_text = "नाम: अमित कुमार | पता: नई दिल्ली | फोन: +91 9988776655"
    response = client.post(
        "/api/documents/upload",
        files={"file": ("hindi_doc.txt", unicode_text.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201
    data = response.json()
    assert "अमित कुमार" in data["extracted_text"]
    assert data["text_length"] == len(unicode_text)

    # Clean up
    client.delete(f"/api/documents/{data['document_id']}")


def test_api_upload_invalid_extension(client):
    """Test rejection of unsupported file extensions (e.g. .exe, .sh, .docx)."""
    response = client.post(
        "/api/documents/upload",
        files={"file": ("malicious.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]


def test_api_upload_binary_in_txt(client):
    """Test rejection of binary files masquerading as .txt."""
    fake_txt = b"Some header\x00\x00\xff\xfeBinary payload"
    response = client.post(
        "/api/documents/upload",
        files={"file": ("fake.txt", fake_txt, "text/plain")},
    )
    assert response.status_code == 400
    assert "binary data" in response.json()["detail"].lower()


def test_api_upload_oversized():
    """Verify security rejection for files exceeding MAX_UPLOAD_SIZE_MB."""
    with pytest.raises(Exception) as exc:
        # 21 MB payload
        large_payload = b"A" * (21 * 1024 * 1024)
        validate_file_upload("large.txt", large_payload)
    assert "413" in str(exc.value) or "exceeds maximum" in str(exc.value).lower()


def test_api_nonexistent_document(client):
    """Test GET /api/documents/{id} returns 404 for unknown ID."""
    response = client.get("/api/documents/nonexistent123")
    assert response.status_code == 404


def test_api_documents_overview_telemetry(client):
    """Test GET /api/documents returns operational telemetry without leaking raw PII."""
    txt_content = "Patient: Rajesh Kulkarni\nEmail: rajesh@example.com\nPhone: +91 9876543210\n"
    up_resp = client.post(
        "/api/documents/upload",
        files={"file": ("telemetry_check.txt", txt_content.encode("utf-8"), "text/plain")},
    )
    assert up_resp.status_code == 201
    doc_id = up_resp.json()["document_id"]

    overview_resp = client.get("/api/documents")
    assert overview_resp.status_code == 200
    payload = overview_resp.json()
    assert payload["total_documents"] >= 1
    assert "awaiting_review_count" in payload
    assert "verified_exports_count" in payload
    assert "suppressed_summaries_count" in payload
    assert "category_distribution" in payload
    assert any(d["document_id"] == doc_id for d in payload["recent_documents"])
    # Ensure raw PII is never leaked in overview payload
    raw_json_str = overview_resp.text
    assert "Rajesh Kulkarni" not in raw_json_str
    assert "rajesh@example.com" not in raw_json_str

    client.delete(f"/api/documents/{doc_id}")
