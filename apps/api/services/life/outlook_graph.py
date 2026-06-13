from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from models import LifeOutlookConnection
from services.life.outlook_oauth import refresh_access_token

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


async def ensure_valid_token(
    connection: LifeOutlookConnection, db: AsyncSession
) -> str:
    if not connection.refresh_token:
        raise ValueError("Outlook is not connected for this workspace")

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


async def _graph_get(
    access_token: str,
    path: str,
    params: dict | None = None,
    *,
    extra_headers: dict[str, str] | None = None,
) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    if extra_headers:
        headers.update(extra_headers)
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.get(
            f"{_GRAPH_BASE}{path}",
            headers=headers,
            params=params or {},
        )
        response.raise_for_status()
        return response.json()


async def fetch_profile_email(access_token: str) -> str | None:
    data = await _graph_get(access_token, "/me", params={"$select": "mail,userPrincipalName"})
    return data.get("mail") or data.get("userPrincipalName")


async def fetch_inbox_messages(
    access_token: str, *, top: int = 25
) -> list[dict[str, Any]]:
    params = {
        "$top": str(top),
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
    }
    data = await _graph_get(access_token, "/me/mailFolders/inbox/messages", params=params)
    return list(data.get("value") or [])


async def fetch_calendar_events(
    access_token: str, *, days: int = 7
) -> list[dict[str, Any]]:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)
    params = {
        "startDateTime": start.isoformat().replace("+00:00", "Z"),
        "endDateTime": end.isoformat().replace("+00:00", "Z"),
        "$select": "id,subject,start,end,location,isAllDay,organizer",
        "$orderby": "start/dateTime",
    }
    data = await _graph_get(
        access_token,
        "/me/calendarview",
        params=params,
        extra_headers={"Prefer": 'outlook.timezone="UTC"'},
    )
    return list(data.get("value") or [])


def parse_graph_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    cleaned = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return datetime.utcnow()
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
