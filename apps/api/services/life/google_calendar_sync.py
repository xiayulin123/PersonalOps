from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete

from database import SessionLocal
from models import LifeCalendarEvent, LifeGoogleConnection
from services.life.google_client import (
    ensure_valid_google_token,
    fetch_google_calendar_events,
    parse_google_event_datetime,
)

logger = logging.getLogger(__name__)


async def sync_workspace_google_calendar(workspace_id: str, *, days: int = 7) -> int:
    async with SessionLocal() as db:
        connection = await db.get(LifeGoogleConnection, workspace_id)
        if connection is None or not connection.enabled or not connection.refresh_token:
            return 0

        try:
            token = await ensure_valid_google_token(connection, db)
            events = await fetch_google_calendar_events(token, days=days)
        except Exception as exc:
            logger.warning(
                "Google calendar sync failed workspace=%s: %s", workspace_id, exc
            )
            return 0

        await db.execute(
            delete(LifeCalendarEvent).where(
                LifeCalendarEvent.workspace_id == workspace_id,
                LifeCalendarEvent.provider == "google",
            )
        )

        now = datetime.utcnow()
        for event in events:
            graph_id = event.get("id")
            if not graph_id:
                continue
            start = event.get("start", {})
            end = event.get("end", {})
            db.add(
                LifeCalendarEvent(
                    workspace_id=workspace_id,
                    provider="google",
                    graph_event_id=graph_id,
                    subject=(event.get("summary") or "(no title)")[:512],
                    start_at=parse_google_event_datetime(start),
                    end_at=parse_google_event_datetime(end),
                    location=(event.get("location") or "")[:512] or None,
                    is_all_day=bool(start.get("date") and not start.get("dateTime")),
                    organizer=None,
                    synced_at=now,
                )
            )

        connection.last_calendar_sync_at = now
        await db.commit()
        return len(events)
