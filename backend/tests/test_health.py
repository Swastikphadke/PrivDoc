"""Unit tests for health endpoint, CORS, and security configuration."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.security import validate_local_host, sanitize_filename


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_root_health_endpoint(client):
    """Verify GET /health returns valid response satisfying NFR-001/NFR-006."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["app_name"] == "PrivyDoc"
    assert data["version"] == "0.1.0"
    assert data["local_privacy_mode"] is True
    assert data["database_connected"] is True


def test_api_health_endpoint(client):
    """Verify GET /api/health also returns valid health payload."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "PrivyDoc"
    assert data["database_connected"] is True


def test_root_endpoint(client):
    """Verify GET / returns service identity and local mode."""
    response = client.get("/api/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "PrivyDoc"
    assert "local-first" in data["mode"]


def test_local_host_validation():
    """Verify non-localhost binding raises security error."""
    validate_local_host("127.0.0.1")
    validate_local_host("localhost")
    with pytest.raises(ValueError) as excinfo:
        validate_local_host("0.0.0.0")
    assert "Security violation" in str(excinfo.value)


def test_sanitize_filename():
    """Verify path traversal characters are stripped."""
    assert sanitize_filename("../../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\cmd.exe") == "cmd.exe"
    assert sanitize_filename("safe_report-2026.pdf") == "safe_report-2026.pdf"


def test_cors_headers(client):
    """Verify CORS is permitted for local frontend origin."""
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
