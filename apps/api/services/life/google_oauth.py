from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from config import settings

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"

_pending_oauth: dict[str, dict[str, Any]] = {}
_OAUTH_SESSION_TTL_SEC = 600


def is_google_configured() -> bool:
    return bool(settings.google_client_id.strip())


def _redirect_uri() -> str:
    uri = settings.life_oauth_google_redirect_uri.strip()
    if uri:
        return uri
    port = settings.life_oauth_callback_port
    return f"http://127.0.0.1:{port}/oauth/google/callback"


def _with_client_auth(payload: dict[str, str]) -> dict[str, str]:
    """Attach client_secret when configured (Web application OAuth clients).

    Google Cloud "Web application" clients require client_secret on token exchange.
    "Desktop app" clients use PKCE only — leave secret empty and set
    GOOGLE_PUBLIC_CLIENT=true.
    """
    secret = settings.google_client_secret.strip()
    if secret:
        return {**payload, "client_secret": secret}
    if settings.google_public_client:
        return payload
    raise ValueError(
        "GOOGLE_CLIENT_SECRET is required for Web OAuth clients. "
        "Add it to .env, or create a Desktop OAuth client and set GOOGLE_PUBLIC_CLIENT=true."
    )


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
    if not is_google_configured():
        raise ValueError("Google is not configured. Set GOOGLE_CLIENT_ID in .env")

    state = str(uuid.uuid4())
    code_verifier, code_challenge = _generate_pkce()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_OAUTH_SESSION_TTL_SEC)

    _pending_oauth[state] = {
        "workspace_id": workspace_id,
        "code_verifier": code_verifier,
        "expires_at": expires_at,
    }

    params = {
        "client_id": settings.google_client_id,
        "response_type": "code",
        "redirect_uri": _redirect_uri(),
        "scope": settings.life_google_scopes,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    authorize_url = f"{_AUTHORIZE_URL}?{urlencode(params)}"
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
            "client_id": settings.google_client_id,
            "code": code,
            "redirect_uri": _redirect_uri(),
            "code_verifier": pending["code_verifier"],
        }
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(_TOKEN_URL, data=token_payload)
        if response.status_code >= 400:
            body = response.json()
            desc = body.get("error_description", body.get("error", "Token exchange failed"))
            if "client_secret is missing" in str(desc).lower():
                raise ValueError(
                    "Google requires GOOGLE_CLIENT_SECRET for this client (even Desktop type). "
                    "Copy Client secret from Google Cloud Console → Credentials → your OAuth client, "
                    "add it to personalops/apps/api/.env, and restart the API."
                )
            raise ValueError(desc)
        data = response.json()

    _pending_oauth.pop(state, None)
    return _token_result_from_response(data)


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    payload = _with_client_auth(
        {
            "grant_type": "refresh_token",
            "client_id": settings.google_client_id,
            "refresh_token": refresh_token,
        }
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(_TOKEN_URL, data=payload)
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
