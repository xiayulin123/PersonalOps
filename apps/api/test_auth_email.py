"""Email verification + password reset auth tests."""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-email-auth")
os.environ.setdefault("DEPLOYMENT_MODE", "cloud")
os.environ.setdefault("RESEND_API_KEY", "re_test_key")

from main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


@pytest.mark.asyncio
async def test_register_verify_login_flow(client):
    email = _unique_email("verify")
    password = "password123"

    with (
        patch("services.auth.email_challenges.is_email_delivery_enabled", return_value=True),
        patch(
            "services.auth.email_challenges.send_auth_code_email",
            new_callable=AsyncMock,
        ) as send_mock,
    ):
        start = await client.post(
            "/auth/register/start",
            json={"email": email, "password": password},
        )
        assert start.status_code == 200, start.text
        assert send_mock.await_count == 1
        sent_code = send_mock.await_args.kwargs["code"]

        verify = await client.post(
            "/auth/register/verify",
            json={"email": email, "code": sent_code},
        )
        assert verify.status_code == 201, verify.text
        token = verify.json()["access_token"]

    login = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == email


@pytest.mark.asyncio
async def test_legacy_register_blocked_when_resend_configured(client):
    email = _unique_email("legacy")
    with patch("routers.auth.is_email_delivery_enabled", return_value=True):
        res = await client.post(
            "/auth/register",
            json={"email": email, "password": "password123"},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_forgot_and_reset_password(client):
    email = _unique_email("reset")
    password = "password123"
    new_password = "newpassword456"

    with (
        patch("services.auth.email_challenges.is_email_delivery_enabled", return_value=True),
        patch(
            "services.auth.email_challenges.send_auth_code_email",
            new_callable=AsyncMock,
        ) as send_mock,
    ):
        start = await client.post(
            "/auth/register/start",
            json={"email": email, "password": password},
        )
        assert start.status_code == 200
        reg_code = send_mock.await_args.kwargs["code"]
        verify = await client.post(
            "/auth/register/verify",
            json={"email": email, "code": reg_code},
        )
        assert verify.status_code == 201

        send_mock.reset_mock()
        forgot = await client.post(
            "/auth/forgot-password",
            json={"email": email},
        )
        assert forgot.status_code == 200
        reset_code = send_mock.await_args.kwargs["code"]

        reset = await client.post(
            "/auth/reset-password",
            json={"email": email, "code": reset_code, "new_password": new_password},
        )
        assert reset.status_code == 200, reset.text

    old_login = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/auth/login",
        json={"email": email, "password": new_password},
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_same_message(client):
    with (
        patch("services.auth.email_challenges.is_email_delivery_enabled", return_value=True),
        patch(
            "services.auth.email_challenges.send_auth_code_email",
            new_callable=AsyncMock,
        ) as send_mock,
    ):
        res = await client.post(
            "/auth/forgot-password",
            json={"email": _unique_email("missing")},
        )
        assert res.status_code == 200
        assert "registered" in res.json()["message"].lower()
        send_mock.assert_not_awaited()
