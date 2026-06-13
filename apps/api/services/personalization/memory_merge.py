from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Memory, Workspace
from services.personalization.settings import effective_personalization_prefs


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def merge_distilled_items(
    db: AsyncSession,
    workspace_id: str,
    items: list[dict],
    *,
    period_start: date | None,
) -> int:
    """Upsert auto-learned memory rows. Returns count of rows written."""
    if not items:
        return 0

    result = await db.execute(
        select(Memory).where(Memory.workspace_id == workspace_id)
    )
    existing = {(row.key, row.kind): row for row in result.scalars().all()}
    written = 0
    now = _utc_now()
    workspace = await db.get(Workspace, workspace_id)
    prefs = effective_personalization_prefs(workspace) if workspace else None
    require_approval = (
        prefs.require_approval
        if prefs is not None
        else settings.auto_memory_require_approval
    )
    default_status = "pending" if require_approval else "active"

    for item in items:
        key = item["key"]
        kind = item.get("kind", "memory")
        value = item["value"]
        confidence = float(item.get("confidence", 0.7))
        lookup = (key, kind)
        row = existing.get(lookup)

        if row is not None and row.source == "manual":
            continue

        if row is not None and row.source == "auto":
            if confidence < row.confidence:
                continue
            row.value = value
            row.confidence = confidence
            row.period_start = period_start
            row.updated_at = now
            if row.status == "rejected":
                row.status = default_status
            written += 1
            continue

        new_row = Memory(
            workspace_id=workspace_id,
            key=key,
            value=value,
            source="auto",
            kind=kind,
            status=default_status,
            confidence=confidence,
            period_start=period_start,
            updated_at=now,
        )
        db.add(new_row)
        existing[lookup] = new_row
        written += 1

    return written
