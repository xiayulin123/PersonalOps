from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from config import settings

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_DEVICE_CODE_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode"
_AUTHORIZE_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"

_pending_device: dict[str, dict[str, Any]] = {}
_pending_oauth: dict[str, dict[str, Any]] = {}

_OAUTH_SESSION_TTL_SEC = 600


def is_outlook_configured() -> bool:
    if not settings.ms_graph_client_id.strip():
        return False
    if settings.ms_graph_public_client:
        return True
    return bool(settings.ms_graph_client_secret.strip())


def _tenant() -> str:
    return settings.ms_graph_tenant_id.strip() or "common"


def _redirect_uri() -> str:
    return settings.life_oauth_microsoft_redirect_uri.strip()


def _with_client_auth(payload: dict[str, str]) -> dict[str, str]:
    """Public (desktop) clients use PKCE only; confidential clients send secret."""
    if settings.ms_graph_public_client:
        return payload
    secret = settings.ms_graph_client_secret.strip()
    if secret:
        return {**payload, "client_secret": secret}
    return payload


def _generate_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _token_result_from_response(data: dict[str, Any]) -> dict[str, Any]:
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=int(data.get("expires_in", 3600))
    )
    return {
        "status": "connected",
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at": expires_at,
    }


async def start_authorization_code_flow(workspace_id: str) -> dict[str, Any]:
    if not is_outlook_configured():
        raise ValueError(
            "Microsoft Graph is not configured. Set MS_GRAPH_CLIENT_ID in .env"
        )

    state = str(uuid.uuid4())
    code_verifier, code_challenge = _generate_pkce()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_OAUTH_SESSION_TTL_SEC)

    _pending_oauth[state] = {
        "workspace_id": workspace_id,
        "code_verifier": code_verifier,
        "expires_at": expires_at,
    }

    params = {
        "client_id": settings.ms_graph_client_id,
        "response_type": "code",
        "redirect_uri": _redirect_uri(),
        "scope": settings.life_outlook_scopes,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "response_mode": "query",
    }
    authorize_url = f"{_AUTHORIZE_URL.format(tenant=_tenant())}?{urlencode(params)}"
    return {
        "authorize_url": authorize_url,
        "state": state,
        "expires_in_sec": _OAUTH_SESSION_TTL_SEC,
    }


async def complete_authorization_code_flow(
    workspace_id: str, code: str, state: str
) -> dict[str, Any]:
    pending = _pending_oauth.get(state)
    if pending is None:
        raise ValueError("Invalid or expired OAuth state")

    if pending["workspace_id"] != workspace_id:
        raise ValueError("OAuth state does not match workspace")

    if datetime.now(timezone.utc) > pending["expires_at"]:
        _pending_oauth.pop(state, None)
        raise ValueError("OAuth session expired. Start sign-in again.")

    token_payload = _with_client_auth(
        {
            "grant_type": "authorization_code",
            "client_id": settings.ms_graph_client_id,
            "code": code,
            "redirect_uri": _redirect_uri(),
            "code_verifier": pending["code_verifier"],
        }
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(_TOKEN_URL.format(tenant=_tenant()), data=token_payload)
        if response.status_code >= 400:
            body = response.json()
            raise ValueError(body.get("error_description", body.get("error", "Token exchange failed")))
        data = response.json()

    _pending_oauth.pop(state, None)
    return _token_result_from_response(data)


async def start_device_code_flow(workspace_id: str) -> dict[str, str]:
    if not is_outlook_configured():
        raise ValueError(
            "Microsoft Graph is not configured. Set MS_GRAPH_CLIENT_ID in .env"
        )

    payload = {
        "client_id": settings.ms_graph_client_id,
        "scope": settings.life_outlook_scopes,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(_DEVICE_CODE_URL.format(tenant=_tenant()), data=payload)
        response.raise_for_status()
        data = response.json()

    _pending_device[workspace_id] = {
        "device_code": data["device_code"],
        "interval": int(data.get("interval", 5)),
        "expires_at": datetime.now(timezone.utc)
        + timedelta(seconds=int(data.get("expires_in", 900))),
    }
    return {
        "user_code": data["user_code"],
        "verification_uri": data.get("verification_uri", "https://microsoft.com/devicelogin"),
        "message": data.get(
            "message",
            "To sign in, open the URL and enter the code shown.",
        ),
        "device_code": data["device_code"],
    }


async def poll_device_code_flow(workspace_id: str, device_code: str) -> dict[str, Any]:
    pending = _pending_device.get(workspace_id)
    if pending and pending.get("device_code") != device_code:
        logger.warning("Device code mismatch for workspace %s", workspace_id)

    token_payload = _with_client_auth(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": settings.ms_graph_client_id,
            "device_code": device_code,
        }
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(_TOKEN_URL.format(tenant=_tenant()), data=token_payload)
        if response.status_code == 400:
            body = response.json()
            error = body.get("error", "")
            if error == "authorization_pending":
                return {"status": "pending"}
            if error == "slow_down":
                return {"status": "pending"}
            raise ValueError(body.get("error_description", error))
        response.raise_for_status()
        data = response.json()

    _pending_device.pop(workspace_id, None)
    return _token_result_from_response(data)


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    payload = _with_client_auth(
        {
            "grant_type": "refresh_token",
            "client_id": settings.ms_graph_client_id,
            "refresh_token": refresh_token,
            "scope": settings.life_outlook_scopes,
        }
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(_TOKEN_URL.format(tenant=_tenant()), data=payload)
        response.raise_for_status()
        data = response.json()

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=int(data.get("expires_in", 3600))
    )
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token") or refresh_token,
        "expires_at": expires_at,
    }
