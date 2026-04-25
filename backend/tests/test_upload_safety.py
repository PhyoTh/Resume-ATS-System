"""Upload-endpoint guards: type allowlist, size cap, empty-body rejection."""
import io

import pytest
from fastapi.testclient import TestClient

from app.api import resumes as resumes_module
from app.db.models import Base
from app.db.session import SessionLocal, engine
from app.main import app


@pytest.fixture(autouse=True)
def _reset_db():
    """Each test gets a clean DB so resume IDs / state don't leak across tests."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    with SessionLocal() as db:
        db.rollback()


@pytest.fixture
def client():
    return TestClient(app)


def test_upload_rejects_unsupported_extension(client):
    res = client.post(
        "/api/resumes/upload",
        files={"file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert res.status_code == 415
    assert "not allowed" in res.json()["detail"]


def test_upload_rejects_empty_file(client):
    res = client.post(
        "/api/resumes/upload",
        files={"file": ("blank.pdf", b"", "application/pdf")},
    )
    assert res.status_code == 422
    assert "empty" in res.json()["detail"].lower()


def test_upload_rejects_oversized_file(client, monkeypatch):
    # Pretend the cap is tiny so we don't have to ship megabytes through TestClient.
    monkeypatch.setattr(resumes_module, "MAX_UPLOAD_BYTES", 16)
    body = io.BytesIO(b"X" * 64)
    res = client.post(
        "/api/resumes/upload",
        files={"file": ("oversized.pdf", body, "application/pdf")},
    )
    assert res.status_code == 413
    assert "too large" in res.json()["detail"].lower()


def test_upload_strips_path_chars_from_suffix(client):
    """If a malicious filename slips path separators into the suffix the
    safe-suffix helper must scrub them; otherwise we'd blow up the storage
    path on Windows / strange filesystems."""
    assert resumes_module._safe_suffix("../etc/passwd") == ""
    assert resumes_module._safe_suffix("nice.PDF") == ".pdf"
    assert resumes_module._safe_suffix(None) == ""
    assert resumes_module._safe_suffix("nope.\\zip") == ".zip"
