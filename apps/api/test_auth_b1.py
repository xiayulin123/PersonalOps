"""B1 auth and tenant isolation tests."""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-b1-tests-only")
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


@pytest.mark.asyncio
async def test_register_login_and_workspace_isolation(client):
    email_a = _unique_email("alice")
    email_b = _unique_email("bob")
    password = "password123"

    with patch("routers.auth.is_email_delivery_enabled", return_value=False):
        reg_a = await client.post(
            "/auth/register",
            json={"email": email_a, "password": password},
        )
        assert reg_a.status_code == 201, reg_a.text
        token_a = reg_a.json()["access_token"]

        reg_b = await client.post(
            "/auth/register",
            json={"email": email_b, "password": password},
        )
        assert reg_b.status_code == 201, reg_b.text
        token_b = reg_b.json()["access_token"]

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    ws_a = await client.post(
        "/workspaces",
        headers=headers_a,
        json={"name": "Alice Study", "type": "study"},
    )
    assert ws_a.status_code == 201
    workspace_a_id = ws_a.json()["id"]

    list_b = await client.get("/workspaces", headers=headers_b)
    assert list_b.status_code == 200
    assert all(item["id"] != workspace_a_id for item in list_b.json())

    forbidden = await client.get(f"/workspaces/{workspace_a_id}", headers=headers_b)
    assert forbidden.status_code == 404


@pytest.mark.asyncio
async def test_cloud_requires_auth_for_workspaces(client):
    with patch("services.deployment.settings.deployment_mode", "cloud"):
        res = await client.get("/workspaces")
        assert res.status_code == 401
