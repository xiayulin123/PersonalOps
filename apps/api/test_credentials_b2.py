"""B2 per-user API credentials tests."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-b2-tests-only")
os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", "test-credentials-key-b2-only!!")
os.environ.setdefault("DEPLOYMENT_MODE", "cloud")

from main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


async def _register(client: AsyncClient, email: str, password: str = "password123") -> str:
    res = await client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_credentials_crud_masked(client):
    token = await _register(client, _unique_email("cred"))
    headers = {"Authorization": f"Bearer {token}"}

    listed = await client.get("/me/credentials", headers=headers)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 2
    assert all(not item["configured"] for item in items)

    saved = await client.put(
        "/me/credentials",
        headers=headers,
        json={"provider": "openai", "secret": "sk-test-openai-key-12345678"},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["configured"] is True
    assert body["masked"].startswith("sk-t")
    assert "12345678" in body["masked"]

    listed2 = await client.get("/me/credentials", headers=headers)
    openai_row = next(i for i in listed2.json()["items"] if i["provider"] == "openai")
    assert openai_row["configured"] is True

    removed = await client.put(
        "/me/credentials",
        headers=headers,
        json={"provider": "openai", "secret": ""},
    )
    assert removed.status_code == 200
    assert removed.json()["configured"] is False


@pytest.mark.asyncio
async def test_chat_requires_openai_key_in_cloud(client):
    token = await _register(client, _unique_email("nokey"))
    headers = {"Authorization": f"Bearer {token}"}

    ws = await client.post(
        "/workspaces",
        headers=headers,
        json={"name": "Test", "type": "study"},
    )
    assert ws.status_code == 201
    workspace_id = ws.json()["id"]

    chat = await client.post(
        f"/workspaces/{workspace_id}/chat",
        headers=headers,
        json={"message": "Hello"},
    )
    assert chat.status_code == 400
    assert "OpenAI" in chat.json()["detail"]

    await client.put(
        "/me/credentials",
        headers=headers,
        json={"provider": "openai", "secret": "sk-test-openai-key-12345678"},
    )

    chat2 = await client.post(
        f"/workspaces/{workspace_id}/chat",
        headers=headers,
        json={"message": "Hello"},
    )
    assert chat2.status_code in (200, 500), chat2.text
