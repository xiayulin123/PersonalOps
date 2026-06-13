from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import PromptLog, PromptPeriodStats, Workspace
from services.personalization.redact import redact_secrets


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def week_start(day: date) -> date:
    """Monday of the ISO week containing day."""
    return day - timedelta(days=day.weekday())


async def _bump_period_stat(
    db: AsyncSession,
    workspace_id: str,
    period_type: str,
    period_start: date,
) -> None:
    result = await db.execute(
        select(PromptPeriodStats).where(
            PromptPeriodStats.workspace_id == workspace_id,
            PromptPeriodStats.period_type == period_type,
            PromptPeriodStats.period_start == period_start,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(
            PromptPeriodStats(
                workspace_id=workspace_id,
                period_type=period_type,
                period_start=period_start,
                prompt_count=1,
                distillation_status="pending",
            )
        )
        return

    row.prompt_count += 1
    if row.distillation_status == "skipped":
        row.distillation_status = "pending"


async def record_user_prompt(
    db: AsyncSession,
    *,
    workspace_id: str,
    conversation_id: str,
    message_id: str,
    content: str,
    chat_mode: str,
) -> PromptLog | None:
    """Append one user prompt log row and bump day/week counters."""
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        return None
    from services.personalization.settings import effective_personalization_prefs

    if not effective_personalization_prefs(workspace).auto_learn_enabled:
        return None

    text = content.strip()
    if not text:
        return None

    now = _utc_now()
    today = now.date()
    week_monday = week_start(today)

    entry = PromptLog(
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        message_id=message_id,
        role="user",
        content=text,
        content_redacted=redact_secrets(text),
        chat_mode=chat_mode,
        char_count=len(text),
        created_at=now,
    )
    db.add(entry)
    await _bump_period_stat(db, workspace_id, "day", today)
    await _bump_period_stat(db, workspace_id, "week", week_monday)
    return entry


async def get_personalization_stats(
    db: AsyncSession, workspace_id: str
) -> dict[str, int | str | bool]:
    today = _utc_now().date()
    week_monday = week_start(today)

    day_row = await db.execute(
        select(PromptPeriodStats).where(
            PromptPeriodStats.workspace_id == workspace_id,
            PromptPeriodStats.period_type == "day",
            PromptPeriodStats.period_start == today,
        )
    )
    week_row = await db.execute(
        select(PromptPeriodStats).where(
            PromptPeriodStats.workspace_id == workspace_id,
            PromptPeriodStats.period_type == "week",
            PromptPeriodStats.period_start == week_monday,
        )
    )
    day_stat = day_row.scalar_one_or_none()
    week_stat = week_row.scalar_one_or_none()
    workspace = await db.get(Workspace, workspace_id)
    from services.personalization.settings import effective_personalization_prefs

    enabled = (
        effective_personalization_prefs(workspace).auto_learn_enabled
        if workspace is not None
        else settings.personalization_enabled
    )

    return {
        "enabled": enabled,
        "today_count": day_stat.prompt_count if day_stat else 0,
        "week_count": week_stat.prompt_count if week_stat else 0,
        "daily_threshold": settings.prompt_daily_threshold,
        "weekly_threshold": settings.prompt_weekly_threshold,
        "today_distillation_status": (
            day_stat.distillation_status if day_stat else "pending"
        ),
        "week_distillation_status": (
            week_stat.distillation_status if week_stat else "pending"
        ),
        "period_day": today.isoformat(),
        "period_week_start": week_monday.isoformat(),
    }


async def resolve_workspace_chat_mode(
    db: AsyncSession, workspace_id: str
) -> str:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        return settings.chat_default_mode
    return workspace.chat_mode or settings.chat_default_mode
