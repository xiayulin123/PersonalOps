from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import SessionLocal
from models import PromptLog, Workspace
from services.personalization.archive import archive_is_configured, get_prompt_archive

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _day_bounds(period_start: date) -> tuple[datetime, datetime]:
    start = datetime.combine(period_start, time.min)
    end = datetime.combine(period_start + timedelta(days=1), time.min)
    return start, end


async def fetch_redacted_prompt_records(
    db: AsyncSession,
    workspace_id: str,
    period_start: date,
) -> list[dict[str, Any]]:
    start, end = _day_bounds(period_start)
    result = await db.execute(
        select(PromptLog)
        .where(
            PromptLog.workspace_id == workspace_id,
            PromptLog.created_at >= start,
            PromptLog.created_at < end,
        )
        .order_by(PromptLog.created_at.asc())
    )
    records: list[dict[str, Any]] = []
    for row in result.scalars().all():
        text = (row.content_redacted or row.content or "").strip()
        if not text:
            continue
        records.append(
            {
                "id": row.id,
                "conversation_id": row.conversation_id,
                "message_id": row.message_id,
                "content_redacted": text,
                "char_count": row.char_count,
                "chat_mode": row.chat_mode,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return records


async def archive_workspace_period(
    db: AsyncSession,
    workspace_id: str,
    period_start: date,
    *,
    force: bool = False,
) -> dict[str, Any]:
    if not settings.cloud_archive_enabled:
        return {"status": "disabled", "record_count": 0}
    if not archive_is_configured():
        return {
            "status": "misconfigured",
            "record_count": 0,
            "error": "Cloud archive enabled but bucket/key not configured",
        }

    archive = get_prompt_archive()
    if not force and await asyncio.to_thread(
        archive.object_exists, workspace_id, period_start
    ):
        return {
            "status": "skipped",
            "record_count": 0,
            "reason": "already archived",
        }

    records = await fetch_redacted_prompt_records(db, workspace_id, period_start)
    if not records:
        return {
            "status": "skipped",
            "record_count": 0,
            "reason": "no prompts in period",
        }

    try:
        uri = await asyncio.to_thread(
            archive.upload_period, workspace_id, period_start, records
        )
    except Exception as exc:
        logger.warning(
            "Archive upload failed workspace=%s period=%s: %s",
            workspace_id,
            period_start,
            exc,
        )
        return {"status": "failed", "record_count": 0, "error": str(exc)}

    return {
        "status": "done",
        "record_count": len(records),
        "uri": uri,
    }


async def archive_single_workspace(
    workspace_id: str,
    *,
    period_start: date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    period_start = period_start or (_utc_now().date() - timedelta(days=1))

    async with SessionLocal() as db:
        outcome = await archive_workspace_period(
            db, workspace_id, period_start, force=force
        )
        return {
            "workspace_id": workspace_id,
            "period_start": period_start.isoformat(),
            **outcome,
        }


async def run_archive_pass(
    *,
    period_start: date | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    period_start = period_start or (_utc_now().date() - timedelta(days=1))

    async with SessionLocal() as db:
        workspace_ids = list((await db.execute(select(Workspace.id))).scalars().all())
        results: list[dict[str, Any]] = []
        for workspace_id in workspace_ids:
            outcome = await archive_workspace_period(
                db, workspace_id, period_start, force=force
            )
            results.append(
                {
                    "workspace_id": workspace_id,
                    "period_start": period_start.isoformat(),
                    **outcome,
                }
            )
        return results
