"""Demo account helpers."""

from __future__ import annotations

from fastapi import HTTPException

from config import settings
from models import User


def is_demo_user(user: User | None) -> bool:
    return bool(user and user.is_demo)


def demo_credential_blocked_message() -> str:
    return (
        "The example account uses platform API keys. "
        "You cannot add or change API keys on this account."
    )


def assert_demo_can_edit_credentials(user: User) -> None:
    if is_demo_user(user):
        raise HTTPException(status_code=403, detail=demo_credential_blocked_message())


def platform_credentials_for_demo() -> dict[str, str]:
    """Inject server-side keys for demo users (never stored in user_api_credentials)."""
    out: dict[str, str] = {}
    openai = settings.openai_api_key.strip()
    if openai:
        out["openai"] = openai
    tavily = settings.tavily_api_key.strip()
    if tavily:
        out["tavily"] = tavily
    return out


def demo_openai_configured() -> bool:
    return bool(settings.openai_api_key.strip())
