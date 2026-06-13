from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from config import settings
from services.personalization.archive_job import run_archive_pass
from services.personalization.distillation import cleanup_prompt_logs, run_distillation_pass
from services.personalization.prompt_log import week_start

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SEC = 300
_last_daily_key: str | None = None
_last_weekly_key: str | None = None
_last_cleanup_day: date | None = None
_last_archive_day: date | None = None


def _schedule_enabled(period_type: str) -> bool:
    mode = settings.personalization_distill_schedule.strip().lower()
    if mode == "both":
        return True
    return mode == period_type


async def _maybe_run_scheduled_jobs() -> None:
    global _last_daily_key, _last_weekly_key, _last_cleanup_day, _last_archive_day

    if not settings.personalization_enabled:
        return

    from datetime import datetime, timezone

    utc = datetime.now(timezone.utc)
    today = utc.date()
    hour = utc.hour
    minute = utc.minute

    if _last_cleanup_day != today and hour == 3 and minute < 10:
        deleted = await cleanup_prompt_logs()
        if deleted:
            logger.info("Prompt log retention deleted %s rows", deleted)
        _last_cleanup_day = today

    if (
        settings.cloud_archive_enabled
        and _last_archive_day != today
        and hour == 0
        and 25 <= minute < 35
    ):
        yesterday = today - timedelta(days=1)
        logger.info("Running scheduled cloud archive for %s", yesterday)
        await run_archive_pass(period_start=yesterday)
        _last_archive_day = today

    if hour == 23 and minute >= 55:
        daily_key = today.isoformat()
        if _schedule_enabled("day") and _last_daily_key != daily_key:
            logger.info("Running scheduled daily distillation for %s", today)
            await run_distillation_pass("day", period_start=today)
            _last_daily_key = daily_key

        if today.weekday() == 6:
            week_key = week_start(today).isoformat()
            if _schedule_enabled("week") and _last_weekly_key != week_key:
                logger.info("Running scheduled weekly distillation for %s", week_key)
                await run_distillation_pass("week", period_start=week_start(today))
                _last_weekly_key = week_key


async def personalization_scheduler_loop() -> None:
    while True:
        try:
            await _maybe_run_scheduled_jobs()
        except Exception:
            logger.exception("Personalization scheduler tick failed")
        await asyncio.sleep(_CHECK_INTERVAL_SEC)


def start_personalization_scheduler() -> asyncio.Task:
    return asyncio.create_task(personalization_scheduler_loop())
