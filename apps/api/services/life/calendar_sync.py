from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete

from database import SessionLocal
from models import LifeCalendarEvent, LifeOutlookConnection
from services.life.outlook_graph import (
    ensure_valid_token,
    fetch_calendar_events,
    parse_graph_datetime,
)

logger = logging.getLogger(__name__)


async def sync_workspace_calendar(workspace_id: str, *, days: int = 7) -> int:
    async with SessionLocal() as db:
        connection = await db.get(LifeOutlookConnection, workspace_id)
        if connection is None or not connection.enabled or not connection.refresh_token:
            return 0

        try:
            token = await ensure_valid_token(connection, db)
            events = await fetch_calendar_events(token, days=days)
        except Exception as exc:
            logger.warning("Calendar sync failed workspace=%s: %s", workspace_id, exc)
            return 0

        await db.execute(
            delete(LifeCalendarEvent).where(
                LifeCalendarEvent.workspace_id == workspace_id,
                LifeCalendarEvent.provider == "microsoft",
            )
        )

        now = datetime.utcnow()
        for event in events:
            graph_id = event.get("id")
            if not graph_id:
                continue
            start = event.get("start", {})
            end = event.get("end", {})
            organizer = (event.get("organizer") or {}).get("emailAddress", {})
            org_name = organizer.get("name") or organizer.get("address")

            db.add(
                LifeCalendarEvent(
                    workspace_id=workspace_id,
                    provider="microsoft",
                    graph_event_id=graph_id,
                    subject=(event.get("subject") or "(no title)")[:512],
                    start_at=parse_graph_datetime(start.get("dateTime") or start.get("date")),
                    end_at=parse_graph_datetime(end.get("dateTime") or end.get("date")),
                    location=(event.get("location") or {}).get("displayName"),
                    is_all_day=bool(event.get("isAllDay")),
                    organizer=org_name,
                    synced_at=now,
                )
            )

        connection.last_calendar_sync_at = now
        await db.commit()
        return len(events)
