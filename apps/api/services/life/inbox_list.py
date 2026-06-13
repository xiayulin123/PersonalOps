from __future__ import annotations

import math

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import LifeInboxBrief
from services.life.email_summarizer import summarize_email

_PAGE_SIZE_MIN = 3
_PAGE_SIZE_MAX = 10


def clamp_page_size(size: int) -> int:
    return max(_PAGE_SIZE_MIN, min(_PAGE_SIZE_MAX, size))


async def _summarize_brief(brief: LifeInboxBrief) -> None:
    summary, engine = await summarize_email(
        subject=brief.subject,
        from_name=brief.from_name,
        from_address=brief.from_address,
        body_preview=brief.body_preview,
    )
    brief.summary = summary
    brief.summary_engine = engine


async def build_inbox_lists(
    db: AsyncSession,
    workspace_id: str,
    page_size: int,
    page: int = 0,
) -> tuple[list[LifeInboxBrief], list[LifeInboxBrief], int, int]:
    """Return (page_items, viewed, total_unread, total_pages)."""
    size = clamp_page_size(page_size)
    page = max(0, page)

    active = await db.execute(
        select(LifeInboxBrief)
        .where(
            LifeInboxBrief.workspace_id == workspace_id,
            LifeInboxBrief.dismissed.is_(False),
        )
        .order_by(LifeInboxBrief.received_at.desc())
    )
    active_rows = list(active.scalars().all())

    unread_active = [
        row for row in active_rows if row.summary_engine != "raw"
    ]
    total_unread = len(unread_active)
    total_pages = max(1, math.ceil(total_unread / size)) if total_unread else 0
    if total_pages and page >= total_pages:
        page = total_pages - 1

    start = page * size
    page_items = unread_active[start : start + size]

    for brief in page_items:
        if brief.summary_engine == "pending":
            await _summarize_brief(brief)
    if page_items:
        await db.commit()

    viewed_result = await db.execute(
        select(LifeInboxBrief)
        .where(
            LifeInboxBrief.workspace_id == workspace_id,
            or_(
                LifeInboxBrief.dismissed.is_(True),
                LifeInboxBrief.summary_engine == "raw",
            ),
        )
        .order_by(LifeInboxBrief.received_at.desc())
        .limit(50)
    )
    viewed = list(viewed_result.scalars().all())

    return page_items, viewed, total_unread, total_pages
