from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import SessionLocal
from models import PromptLog, PromptPeriodStats, Workspace
from services.auth.openai_access import credentials_for_workspace_owner
from services.deployment import is_cloud_deployment
from services.openai_runtime import MISSING_OPENAI_KEY_MESSAGE
from services.personalization.distiller import distill_prompts_sync
from services.personalization.memory_merge import merge_distilled_items
from services.personalization.prompt_log import week_start
from services.cursor_agent.memory_sync import sync_cursor_memory_file

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _period_bounds(period_type: str, period_start: date) -> tuple[datetime, datetime]:
    start = datetime.combine(period_start, time.min)
    if period_type == "day":
        end = datetime.combine(period_start + timedelta(days=1), time.min)
    else:
        end = datetime.combine(period_start + timedelta(days=7), time.min)
    return start, end


def _threshold_for(period_type: str) -> int:
    if period_type == "week":
        return settings.prompt_weekly_threshold
    return settings.prompt_daily_threshold


async def _fetch_prompt_text(
    db: AsyncSession,
    workspace_id: str,
    period_type: str,
    period_start: date,
) -> str:
    start, end = _period_bounds(period_type, period_start)
    result = await db.execute(
        select(PromptLog)
        .where(
            PromptLog.workspace_id == workspace_id,
            PromptLog.created_at >= start,
            PromptLog.created_at < end,
        )
        .order_by(PromptLog.created_at.asc())
    )
    lines = [
        (row.content_redacted or row.content).strip()
        for row in result.scalars().all()
        if (row.content_redacted or row.content).strip()
    ]
    return "\n---\n".join(lines)


async def _resolve_distill_openai_key(
    db: AsyncSession,
    workspace: Workspace | None,
) -> str:
    """Cloud: workspace owner's Settings key. Local: same, then server .env fallback."""
    if workspace and workspace.user_id:
        credentials = await credentials_for_workspace_owner(db, workspace)
        user_key = (credentials.get("openai") or "").strip()
        if user_key:
            return user_key
        if is_cloud_deployment():
            raise ValueError(MISSING_OPENAI_KEY_MESSAGE)

    env_key = settings.openai_api_key.strip()
    if env_key:
        return env_key

    raise ValueError(MISSING_OPENAI_KEY_MESSAGE if is_cloud_deployment() else (
        "OPENAI_API_KEY is required for prompt distillation"
    ))


async def distill_workspace_period(
    db: AsyncSession,
    workspace_id: str,
    period_type: str,
    period_start: date,
    *,
    force: bool = False,
) -> dict[str, str | int | bool]:
    from services.personalization.settings import effective_personalization_prefs

    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or not effective_personalization_prefs(workspace).auto_learn_enabled:
        return {"status": "disabled", "written": 0}

    stat_result = await db.execute(
        select(PromptPeriodStats).where(
            PromptPeriodStats.workspace_id == workspace_id,
            PromptPeriodStats.period_type == period_type,
            PromptPeriodStats.period_start == period_start,
        )
    )
    stat = stat_result.scalar_one_or_none()
    threshold = _threshold_for(period_type)

    if stat is None:
        stat = PromptPeriodStats(
            workspace_id=workspace_id,
            period_type=period_type,
            period_start=period_start,
            prompt_count=0,
            distillation_status="pending",
        )
        db.add(stat)
        await db.flush()

    if stat.distillation_status == "done" and not force:
        return {"status": "done", "written": 0, "skipped": True}

    if stat.prompt_count < threshold and not force:
        stat.distillation_status = "skipped"
        return {
            "status": "skipped",
            "written": 0,
            "reason": f"count {stat.prompt_count} < threshold {threshold}",
        }

    stat.distillation_status = "running"
    await db.flush()

    prompts_text = await _fetch_prompt_text(db, workspace_id, period_type, period_start)
    if not prompts_text.strip():
        stat.distillation_status = "skipped"
        return {"status": "skipped", "written": 0, "reason": "no prompts in period"}

    period_label = f"{period_type} starting {period_start.isoformat()}"
    try:
        openai_key = await _resolve_distill_openai_key(db, workspace)
        payload = await asyncio.to_thread(
            distill_prompts_sync,
            prompts_text,
            period_label=period_label,
            openai_api_key=openai_key,
        )
    except Exception as exc:
        logger.warning(
            "Distillation failed workspace=%s period=%s %s: %s",
            workspace_id,
            period_type,
            period_start,
            exc,
        )
        stat.distillation_status = "failed"
        return {"status": "failed", "written": 0, "error": str(exc)}

    items = (
        payload.get("memories", [])
        + payload.get("rules", [])
        + payload.get("habits", [])
    )
    written = await merge_distilled_items(
        db, workspace_id, items, period_start=period_start
    )
    stat.distillation_status = "done"
    stat.distilled_at = _utc_now()
    stat.summary_json = json.dumps(payload, ensure_ascii=False)
    await sync_cursor_memory_file(workspace_id, db)
    return {"status": "done", "written": written}


async def distill_single_workspace(
    workspace_id: str,
    period_type: str,
    *,
    period_start: date | None = None,
    force: bool = False,
) -> dict:
    if period_type == "week":
        period_start = period_start or week_start(_utc_now().date())
    else:
        period_start = period_start or _utc_now().date()

    async with SessionLocal() as db:
        outcome = await distill_workspace_period(
            db,
            workspace_id,
            period_type,
            period_start,
            force=force,
        )
        await db.commit()
        return {
            "workspace_id": workspace_id,
            "period_type": period_type,
            "period_start": period_start.isoformat(),
            **outcome,
        }


async def run_distillation_pass(
    period_type: str,
    *,
    period_start: date | None = None,
    force: bool = False,
) -> list[dict]:
    if period_type == "week":
        period_start = period_start or week_start(_utc_now().date())
    else:
        period_start = period_start or _utc_now().date()

    async with SessionLocal() as db:
        workspaces = list((await db.execute(select(Workspace.id))).scalars().all())
        results: list[dict] = []
        for workspace_id in workspaces:
            outcome = await distill_workspace_period(
                db,
                workspace_id,
                period_type,
                period_start,
                force=force,
            )
            results.append(
                {
                    "workspace_id": workspace_id,
                    "period_type": period_type,
                    "period_start": period_start.isoformat(),
                    **outcome,
                }
            )
        await db.commit()
        return results


async def cleanup_prompt_logs() -> int:
    if not settings.personalization_enabled:
        return 0

    now = _utc_now()
    full_cutoff = now - timedelta(days=settings.prompt_log_retention_days)
    raw_cutoff = now - timedelta(days=settings.prompt_log_raw_retention_days)
    deleted = 0

    async with SessionLocal() as db:
        result = await db.execute(
            delete(PromptLog).where(PromptLog.created_at < full_cutoff)
        )
        deleted = result.rowcount or 0

        raw_rows = await db.execute(
            select(PromptLog).where(
                PromptLog.created_at < raw_cutoff,
                PromptLog.content.is_not(None),
            )
        )
        for row in raw_rows.scalars().all():
            if row.content:
                row.content = ""
        await db.commit()

    return deleted
