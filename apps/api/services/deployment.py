"""Edition / deployment mode helpers (Plan B — cloud vs local desktop)."""

from __future__ import annotations

from fastapi import HTTPException

from config import settings

CLOUD_CURSOR_MESSAGE = (
    "Cursor Agent is available in the Desktop edition only. "
    "Use LangGraph on the cloud web app."
)


def is_cloud_deployment() -> bool:
    return settings.deployment_mode.strip().lower() == "cloud"


def assert_chat_mode_allowed(chat_mode: str) -> None:
    if is_cloud_deployment() and chat_mode == "cursor_agent":
        raise HTTPException(status_code=400, detail=CLOUD_CURSOR_MESSAGE)


def available_chat_modes() -> list[str]:
    if is_cloud_deployment():
        return ["langgraph"]
    return ["langgraph", "cursor_agent"]
