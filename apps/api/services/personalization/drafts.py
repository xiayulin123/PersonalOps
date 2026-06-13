from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Memory, PromptLog, PromptPeriodStats
from services.cursor_agent.memory_sync import sync_cursor_memory_file


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def list_pending_drafts(
    db: AsyncSession, workspace_id: str
) -> list[Memory]:
    result = await db.execute(
        select(Memory)
        .where(
            Memory.workspace_id == workspace_id,
            Memory.source == "auto",
            Memory.status == "pending",
        )
        .order_by(Memory.kind.asc(), Memory.confidence.desc(), Memory.key.asc())
    )
    return list(result.scalars().all())


async def _get_pending_draft_or_404(
    db: AsyncSession, workspace_id: str, memory_id: str
) -> Memory:
    memory = await db.get(Memory, memory_id)
    if (
        memory is None
        or memory.workspace_id != workspace_id
        or memory.source != "auto"
        or memory.status != "pending"
    ):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Pending draft not found")
    return memory


async def adopt_draft(
    db: AsyncSession, workspace_id: str, memory_id: str
) -> Memory:
    memory = await _get_pending_draft_or_404(db, workspace_id, memory_id)
    memory.status = "active"
    memory.updated_at = _utc_now()
    await db.flush()
    await sync_cursor_memory_file(workspace_id, db)
    return memory


async def reject_draft(
    db: AsyncSession, workspace_id: str, memory_id: str
) -> Memory:
    memory = await _get_pending_draft_or_404(db, workspace_id, memory_id)
    memory.status = "rejected"
    memory.updated_at = _utc_now()
    await db.flush()
    return memory


async def adopt_all_drafts(db: AsyncSession, workspace_id: str) -> int:
    drafts = await list_pending_drafts(db, workspace_id)
    if not drafts:
        return 0
    now = _utc_now()
    for memory in drafts:
        memory.status = "active"
        memory.updated_at = now
    await db.flush()
    await sync_cursor_memory_file(workspace_id, db)
    return len(drafts)


async def wipe_personalization_data(db: AsyncSession, workspace_id: str) -> dict[str, int]:
    log_result = await db.execute(
        delete(PromptLog).where(PromptLog.workspace_id == workspace_id)
    )
    stats_result = await db.execute(
        delete(PromptPeriodStats).where(PromptPeriodStats.workspace_id == workspace_id)
    )
    auto_memories = await db.execute(
        select(Memory).where(
            Memory.workspace_id == workspace_id,
            Memory.source == "auto",
        )
    )
    auto_rows = list(auto_memories.scalars().all())
    for row in auto_rows:
        await db.delete(row)
    await db.flush()
    await sync_cursor_memory_file(workspace_id, db)
    return {
        "prompt_logs_deleted": log_result.rowcount or 0,
        "period_stats_deleted": stats_result.rowcount or 0,
        "auto_memory_deleted": len(auto_rows),
    }
