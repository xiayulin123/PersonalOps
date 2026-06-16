"""S1.0 study workspace foundation tests."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-study-s1")
os.environ.setdefault("DEPLOYMENT_MODE", "cloud")
os.environ["RESEND_API_KEY"] = ""

from main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


async def _register(client: AsyncClient, email: str, password: str = "password123") -> str:
    from unittest.mock import patch

    with patch("routers.auth.is_email_delivery_enabled", return_value=False):
        res = await client.post(
            "/auth/register",
            json={"email": email, "password": password},
        )
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_study_sources_404_on_non_study_workspace(client):
    email = _unique_email("study-guard")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}

    ws = await client.post(
        "/workspaces",
        headers=headers,
        json={"name": "Code WS", "type": "code"},
    )
    assert ws.status_code == 201
    workspace_id = ws.json()["id"]

    res = await client.get(
        f"/workspaces/{workspace_id}/study/sources",
        headers=headers,
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_study_sources_lists_ready_files(client):
    email = _unique_email("study-sources")
    token = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}

    ws = await client.post(
        "/workspaces",
        headers=headers,
        json={"name": "CSC369", "type": "study"},
    )
    assert ws.status_code == 201
    workspace_id = ws.json()["id"]

    res = await client.get(
        f"/workspaces/{workspace_id}/study/sources",
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["workspace_id"] == workspace_id
    assert body["ready_count"] == 0
    assert body["files"] == []
