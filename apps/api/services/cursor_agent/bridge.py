from __future__ import annotations

import asyncio
import logging

from config import settings

logger = logging.getLogger("personalops.cursor_agent")

_client = None
_lock = asyncio.Lock()


async def start_cursor_bridge() -> None:
    """Launch cursor-sdk bridge when API key is configured."""
    global _client
    if not settings.cursor_api_key.strip():
        logger.info("CURSOR_API_KEY not set — cursor_agent chat mode unavailable")
        return

    async with _lock:
        if _client is not None:
            return
        from cursor_sdk.asyncio import AsyncClient

        try:
            _client = await asyncio.wait_for(
                AsyncClient.launch_bridge(workspace=settings.data_dir),
                timeout=settings.cursor_bridge_startup_timeout_sec,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Cursor SDK bridge startup timed out after %ss — "
                "API will run; cursor_agent chat retries bridge on demand",
                settings.cursor_bridge_startup_timeout_sec,
            )
            return
        except Exception as exc:
            logger.warning("Cursor SDK bridge failed to start: %s", exc)
            return
        logger.info("Cursor SDK bridge started (workspace=%s)", settings.data_dir)


async def stop_cursor_bridge() -> None:
    global _client
    if _client is None:
        return
    try:
        await _client.aclose()
    except Exception as exc:
        logger.warning("Cursor bridge shutdown: %s", exc)
    finally:
        _client = None


async def get_cursor_client():
    """Return shared AsyncClient or raise if cursor mode is not configured."""
    global _client
    if _client is None and settings.cursor_api_key.strip():
        await start_cursor_bridge()
    if _client is None:
        raise RuntimeError(
            "Cursor Agent is not available. Set CURSOR_API_KEY and restart the API."
        )
    return _client
