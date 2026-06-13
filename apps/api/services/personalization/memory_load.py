from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Memory
from services.agent.state import MemoryItem


async def load_active_memory_items(
    db: AsyncSession, workspace_id: str
) -> list[MemoryItem]:
    result = await db.execute(
        select(Memory)
        .where(
            Memory.workspace_id == workspace_id,
            Memory.status == "active",
        )
        .order_by(Memory.kind.asc(), Memory.key.asc())
    )
    return [
        {
            "key": row.key,
            "value": row.value,
            "kind": row.kind or "memory",
            "source": row.source or "manual",
        }
        for row in result.scalars().all()
    ]
