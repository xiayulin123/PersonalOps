from __future__ import annotations

import logging
import os

import chromadb

from config import settings
from services.deployment import available_chat_modes, is_cloud_deployment
from services.code_search import is_ripgrep_available
from services.life.google_oauth import is_google_configured
from services.life.outlook_oauth import is_outlook_configured
from services.ocr import get_ocr_provider, is_ocr_available

logger = logging.getLogger(__name__)


def _resolve_web_provider() -> str:
    configured = settings.web_search_provider.strip().lower() or "tavily"
    if configured == "duckduckgo":
        return "duckduckgo"
    if settings.tavily_api_key.strip():
        return "tavily"
    return "duckduckgo"


def check_chroma_ok() -> bool:
    try:
        persist_dir = settings.chroma_persist_dir
        os.makedirs(persist_dir, exist_ok=True)
        client = chromadb.PersistentClient(path=persist_dir)
        client.heartbeat()
        return True
    except Exception as exc:
        logger.warning("Chroma health check failed: %s", exc)
        return False


def build_health_payload() -> dict:
    chroma_ok = check_chroma_ok()
    openai_configured = bool(settings.openai_api_key.strip())
    status = "ok" if chroma_ok else "degraded"

    return {
        "status": status,
        "openai_configured": openai_configured,
        "chroma_ok": chroma_ok,
        "web_provider": _resolve_web_provider(),
        "ocr_available": is_ocr_available(),
        "ocr_provider": get_ocr_provider(),
        "github_configured": bool(settings.github_token.strip()),
        "ripgrep_available": is_ripgrep_available(),
        "metrics_enabled": settings.metrics_enabled,
        "cursor_configured": bool(settings.cursor_api_key.strip()),
        "chat_default_mode": settings.chat_default_mode,
        "outlook_configured": is_outlook_configured(),
        "google_configured": is_google_configured(),
        "deployment_mode": settings.deployment_mode,
        "cursor_agent_available": "cursor_agent" in available_chat_modes(),
    }
