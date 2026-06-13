from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from models import LifeGoogleConnection
from services.life.google_oauth import refresh_access_token

logger = logging.getLogger(__name__)

_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"
_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"


async def ensure_valid_google_token(
    connection: LifeGoogleConnection, db: AsyncSession
) -> str:
    if not connection.refresh_token:
        raise ValueError("Google is not connected for this workspace")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if (
        connection.access_token
        and connection.token_expires_at
        and connection.token_expires_at > now + timedelta(minutes=2)
    ):
        return connection.access_token

    tokens = await refresh_access_token(connection.refresh_token)
    connection.access_token = tokens["access_token"]
    connection.refresh_token = tokens["refresh_token"]
    expires = tokens["expires_at"]
    connection.token_expires_at = (
        expires.replace(tzinfo=None) if expires.tzinfo else expires
    )
    await db.commit()
    return connection.access_token


async def _google_get(access_token: str, url: str, params: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.get(url, headers=headers, params=params or {})
        response.raise_for_status()
        return response.json()


async def fetch_google_profile_email(access_token: str) -> str | None:
    data = await _google_get(
        access_token, "https://www.googleapis.com/oauth2/v2/userinfo"
    )
    return data.get("email")


async def fetch_gmail_messages(access_token: str, *, max_results: int = 50) -> list[dict[str, Any]]:
    list_data = await _google_get(
        access_token,
        f"{_GMAIL_BASE}/users/me/messages",
        params={"labelIds": "INBOX", "maxResults": str(max_results)},
    )
    messages: list[dict[str, Any]] = []
    for item in list_data.get("messages") or []:
        msg_id = item.get("id")
        if not msg_id:
            continue
        detail = await _google_get(
            access_token,
            f"{_GMAIL_BASE}/users/me/messages/{msg_id}",
            params={"format": "metadata", "metadataHeaders": "From,Subject,Date"},
        )
        messages.append(detail)
    return messages


def _parse_gmail_received_at(message: dict[str, Any], headers: dict[str, str]) -> datetime:
    internal_ms = message.get("internalDate")
    if internal_ms is not None:
        try:
            return datetime.fromtimestamp(
                int(internal_ms) / 1000, tz=timezone.utc
            ).replace(tzinfo=None)
        except (TypeError, ValueError, OSError):
            pass

    date_header = headers.get("date", "").strip()
    if date_header:
        try:
            return parsedate_to_datetime(date_header).astimezone(
                timezone.utc
            ).replace(tzinfo=None)
        except (TypeError, ValueError, OverflowError):
            pass

    return datetime.utcnow()


def _parse_gmail_from(from_raw: str) -> tuple[str | None, str]:
    cleaned = from_raw.strip()
    if not cleaned:
        return None, "unknown"
    if "<" in cleaned and ">" in cleaned:
        name = cleaned.split("<")[0].strip().strip('"')
        address = cleaned.split("<")[1].split(">")[0].strip()
        return name or None, address or "unknown"
    return None, cleaned


def parse_gmail_message(message: dict[str, Any]) -> dict[str, Any]:
    headers = {
        h.get("name", "").lower(): h.get("value", "")
        for h in message.get("payload", {}).get("headers") or []
    }
    from_name, from_address = _parse_gmail_from(headers.get("from", ""))
    received_at = _parse_gmail_received_at(message, headers)

    return {
        "id": message.get("id"),
        "subject": headers.get("subject") or "(no subject)",
        "from_name": from_name,
        "from_address": from_address,
        "body_preview": message.get("snippet") or "",
        "is_unread": "UNREAD" in (message.get("labelIds") or []),
        "received_at": received_at,
    }


async def fetch_google_calendar_events(
    access_token: str, *, days: int = 7
) -> list[dict[str, Any]]:
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=days)
    params = {
        "timeMin": start.isoformat().replace("+00:00", "Z"),
        "timeMax": end.isoformat().replace("+00:00", "Z"),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "100",
    }
    data = await _google_get(
        access_token,
        f"{_CALENDAR_BASE}/calendars/primary/events",
        params=params,
    )
    return list(data.get("items") or [])


def parse_google_event_datetime(value: dict | None) -> datetime:
    if not value:
        return datetime.utcnow()
    raw = value.get("dateTime") or value.get("date")
    if not raw:
        return datetime.utcnow()
    if "T" not in raw:
        return datetime.fromisoformat(raw)
    cleaned = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return datetime.utcnow()
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
