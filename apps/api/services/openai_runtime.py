"""Per-request OpenAI (and related) API keys via context vars (Plan B B2)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from typing import AsyncIterator

from openai import OpenAI

from config import settings
from services.deployment import is_cloud_deployment

MISSING_OPENAI_KEY_MESSAGE = (
    "Add your OpenAI API key in Settings before using chat or file indexing."
)

_request_credentials: ContextVar[dict[str, str]] = ContextVar(
    "request_credentials", default={}
)

_openai_clients: dict[str, OpenAI] = {}


class MissingOpenAIKeyError(ValueError):
    """Raised when cloud mode requires a user OpenAI key but none is configured."""


def set_request_credentials(credentials: dict[str, str]) -> Token:
    cleaned = {k: v.strip() for k, v in credentials.items() if v and v.strip()}
    return _request_credentials.set(cleaned)


def reset_request_credentials(token: Token) -> None:
    _request_credentials.reset(token)


def get_request_credential(provider: str) -> str | None:
    return _request_credentials.get().get(provider.strip().lower())


def get_tavily_api_key() -> str | None:
    key = get_request_credential("tavily")
    if key:
        return key
    fallback = settings.tavily_api_key.strip()
    return fallback or None


def resolve_openai_api_key(*, allow_env_fallback: bool = True) -> str:
    key = get_request_credential("openai")
    if key:
        return key
    if allow_env_fallback and not is_cloud_deployment():
        env_key = settings.openai_api_key.strip()
        if env_key:
            return env_key
    if is_cloud_deployment():
        raise MissingOpenAIKeyError(MISSING_OPENAI_KEY_MESSAGE)
    raise MissingOpenAIKeyError("OPENAI_API_KEY is required for indexing")


def get_openai_client() -> OpenAI:
    api_key = resolve_openai_api_key()
    client = _openai_clients.get(api_key)
    if client is None:
        client = OpenAI(api_key=api_key)
        _openai_clients[api_key] = client
    return client


@asynccontextmanager
async def user_api_keys_context(credentials: dict[str, str]) -> AsyncIterator[None]:
    token = set_request_credentials(credentials)
    try:
        yield
    finally:
        reset_request_credentials(token)
