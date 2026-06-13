"""B3 GCS file storage tests."""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-b3-tests-only")
os.environ.setdefault("DEPLOYMENT_MODE", "cloud")

from main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_parse_gs_uri():
    from services.storage.gcs_app_storage import parse_gs_uri

    bucket, path = parse_gs_uri("gs://personalops-personal/users/u1/ws/f1/doc.pdf")
    assert bucket == "personalops-personal"
    assert path == "users/u1/ws/f1/doc.pdf"


def test_should_store_local_when_not_cloud():
    from services.storage.file_storage import should_store_uploads_in_gcs

    with patch("services.storage.file_storage.gcs.is_gcs_app_storage_enabled", return_value=True):
        assert should_store_uploads_in_gcs(user_id="user-1") is True
        assert should_store_uploads_in_gcs(user_id=None) is False


def test_save_upload_local_disk(tmp_path):
    from config import settings
    from services.storage.file_storage import save_uploaded_file

    with patch("services.storage.file_storage.gcs.is_gcs_app_storage_enabled", return_value=False):
        object.__setattr__(settings, "data_dir", str(tmp_path))
        file_id, backend, path, gcs_uri, size = save_uploaded_file(
            workspace_id="ws-1",
            user_id="user-1",
            filename="notes.txt",
            content=b"hello",
        )
    assert backend == "local"
    assert gcs_uri is None
    assert size == 5
    assert os.path.isfile(path)


@pytest.mark.asyncio
async def test_storage_status_requires_auth(client):
    res = await client.get("/me/storage/status")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_storage_status_for_authenticated_user(client):
    email = f"b3-{uuid.uuid4().hex[:8]}@example.com"
    reg = await client.post(
        "/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]

    with patch(
        "routers.me.storage_status_for_user",
        return_value={
            "gcs_enabled": True,
            "connection_ok": True,
            "bucket": "personalops-personal",
            "detail": "ok",
            "user_prefix": "users/abc",
            "credentials_path": "users/abc/secrets/credentials.enc",
            "total_bytes": 1024,
            "conversation_exports_count": 2,
            "last_checked_at": "2026-06-13T00:00:00+00:00",
        },
    ):
        res = await client.get(
            "/me/storage/status",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["connection_ok"] is True
    assert body["total_bytes"] == 1024
