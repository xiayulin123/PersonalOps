from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from config import settings
from database import SessionLocal
from models import LifeGoogleConnection, LifeOutlookConnection, Workspace
from services.life.calendar_sync import sync_workspace_calendar
from services.life.gmail_inbox_sync import sync_workspace_gmail
from services.life.google_calendar_sync import sync_workspace_google_calendar
from services.life.google_oauth import is_google_configured
from services.life.inbox_sync import sync_workspace_mail
from services.life.outlook_oauth import is_outlook_configured

logger = logging.getLogger(__name__)

_poller_task: asyncio.Task | None = None


async def _poll_once() -> None:
    if not is_outlook_configured() and not is_google_configured():
        return

    workspace_ids: set[str] = set()
    async with SessionLocal() as db:
        if is_outlook_configured():
            result = await db.execute(
                select(LifeOutlookConnection.workspace_id)
                .join(Workspace, Workspace.id == LifeOutlookConnection.workspace_id)
                .where(
                    LifeOutlookConnection.enabled.is_(True),
                    LifeOutlookConnection.refresh_token.isnot(None),
                    Workspace.type == "life",
                )
            )
            workspace_ids.update(row[0] for row in result.all())
        if is_google_configured():
            result = await db.execute(
                select(LifeGoogleConnection.workspace_id)
                .join(Workspace, Workspace.id == LifeGoogleConnection.workspace_id)
                .where(
                    LifeGoogleConnection.enabled.is_(True),
                    LifeGoogleConnection.refresh_token.isnot(None),
                    Workspace.type == "life",
                )
            )
            workspace_ids.update(row[0] for row in result.all())

    for workspace_id in workspace_ids:
        try:
            await sync_workspace_mail(workspace_id)
            await sync_workspace_calendar(workspace_id)
            await sync_workspace_gmail(workspace_id)
            await sync_workspace_google_calendar(workspace_id)
        except Exception as exc:
            logger.warning("Life poller error workspace=%s: %s", workspace_id, exc)


async def _poll_loop() -> None:
    interval = max(30, settings.life_outlook_poll_sec)
    while True:
        try:
            await _poll_once()
        except Exception as exc:
            logger.warning("Life poller iteration failed: %s", exc)
        await asyncio.sleep(interval)


def start_life_poller() -> None:
    global _poller_task
    if _poller_task is not None:
        return
    _poller_task = asyncio.create_task(_poll_loop())
    logger.info("Life plugin poller started (interval=%ss)", settings.life_outlook_poll_sec)


def stop_life_poller() -> None:
    global _poller_task
    if _poller_task is None:
        return
    _poller_task.cancel()
    _poller_task = None
