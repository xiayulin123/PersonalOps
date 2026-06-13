from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from models import Conversation, Message
from services.agent.state import HistoryMessage
from services.db_ordering import (
    conversations_recent_first,
    messages_oldest_first,
    messages_recent_first,
)


async def load_recent_history(
    conversation_id: str,
    db: AsyncSession,
    *,
    max_turns: int | None = None,
) -> list[HistoryMessage]:
    """Load the most recent conversation turns (user + assistant pairs)."""
    turns = settings.agent_history_turns if max_turns is None else max_turns
    max_messages = max(0, turns) * 2
    if max_messages == 0:
        return []

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(messages_recent_first())
        .limit(max_messages)
    )
    messages = list(reversed(result.scalars().all()))

    history: list[HistoryMessage] = []
    for message in messages:
        if message.role not in ("user", "assistant"):
            continue
        history.append({"role": message.role, "content": message.content})
    return history


def _parse_message_metadata(message: Message) -> dict:
    if not message.sources_json:
        return {
            "sources": [],
            "web_sources": [],
            "trace": [],
            "route": None,
            "chat_engine": None,
            "agent_label": None,
        }

    try:
        payload = json.loads(message.sources_json)
    except json.JSONDecodeError:
        return {
            "sources": [],
            "web_sources": [],
            "trace": [],
            "route": None,
            "chat_engine": None,
            "agent_label": None,
        }

    if not isinstance(payload, dict):
        return {
            "sources": [],
            "web_sources": [],
            "trace": [],
            "route": None,
            "chat_engine": None,
            "agent_label": None,
        }

    return {
        "sources": payload.get("sources") or [],
        "web_sources": payload.get("web_sources") or [],
        "trace": payload.get("trace") or [],
        "route": payload.get("route"),
        "chat_engine": payload.get("chat_engine"),
        "agent_label": payload.get("agent_label"),
    }


def _conversation_title_from_content(content: str) -> str:
    trimmed = content.strip()
    trimmed = re.sub(r"^\[[^\]]+\]\s*", "", trimmed)
    trimmed = re.sub(r"\s+", " ", trimmed)
    if not trimmed:
        return "New Chat"
    if len(trimmed) <= 80:
        return trimmed
    return trimmed[:80] + "..."


async def get_conversation_for_workspace(
    conversation_id: str,
    workspace_id: str,
    db: AsyncSession,
) -> Conversation | None:
    return await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    )


async def get_latest_conversation(
    workspace_id: str,
    db: AsyncSession,
) -> Conversation | None:
    latest_conv_id = await db.scalar(
        select(Message.conversation_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.workspace_id == workspace_id)
        .order_by(messages_recent_first())
        .limit(1)
    )
    if latest_conv_id:
        return await db.get(Conversation, latest_conv_id)

    return await db.scalar(
        select(Conversation)
        .where(Conversation.workspace_id == workspace_id)
        .order_by(conversations_recent_first())
        .limit(1)
    )


async def create_conversation(
    workspace_id: str,
    db: AsyncSession,
    *,
    title: str = "New Chat",
) -> Conversation:
    conversation = Conversation(workspace_id=workspace_id, title=title)
    db.add(conversation)
    await db.flush()
    return conversation


async def _conversation_last_used_at(
    conversation_id: str,
    db: AsyncSession,
) -> datetime | None:
    return await db.scalar(
        select(func.max(Message.created_at)).where(
            Message.conversation_id == conversation_id
        )
    )


async def list_workspace_conversations(
    workspace_id: str,
    db: AsyncSession,
) -> list[dict]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.workspace_id == workspace_id)
        .order_by(conversations_recent_first())
    )
    conversations = result.scalars().all()

    items: list[dict] = []
    for conversation in conversations:
        message_count = await db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation.id)
        )
        last_used_at = await _conversation_last_used_at(conversation.id, db)
        items.append(
            {
                "id": conversation.id,
                "title": conversation.title,
                "message_count": int(message_count or 0),
                "last_used_at": last_used_at,
            }
        )
    items.sort(
        key=lambda item: item["last_used_at"] or datetime.min,
        reverse=True,
    )
    return items


async def load_conversation_messages(
    conversation_id: str,
    db: AsyncSession,
    *,
    limit: int = 200,
) -> list[dict]:
    """Load messages for one conversation (oldest first)."""
    safe_limit = max(1, min(limit, 500))
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .options(selectinload(Message.feedback))
        .order_by(messages_oldest_first())
        .limit(safe_limit)
    )
    messages = result.scalars().all()

    items: list[dict] = []
    for message in messages:
        if message.role not in ("user", "assistant"):
            continue

        metadata = _parse_message_metadata(message)
        feedback_rating = None
        if message.feedback is not None:
            feedback_rating = message.feedback.rating

        items.append(
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "sources": metadata["sources"],
                "web_sources": metadata["web_sources"],
                "trace": metadata["trace"],
                "route": metadata["route"],
                "chat_engine": metadata["chat_engine"],
                "agent_label": metadata["agent_label"],
                "feedback_rating": feedback_rating,
            }
        )
    return items


async def load_workspace_chat_messages(
    workspace_id: str,
    db: AsyncSession,
    *,
    conversation_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Load messages for a workspace conversation."""
    if conversation_id:
        conversation = await get_conversation_for_workspace(
            conversation_id, workspace_id, db
        )
        if conversation is None:
            return []
        return await load_conversation_messages(conversation.id, db, limit=limit)

    conversation = await get_latest_conversation(workspace_id, db)
    if conversation is None:
        return []
    return await load_conversation_messages(conversation.id, db, limit=limit)


async def maybe_update_conversation_title(
    conversation_id: str,
    user_content: str,
    db: AsyncSession,
) -> None:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        return
    if conversation.title.strip() and conversation.title not in ("New Chat", "Chat"):
        return
    conversation.title = _conversation_title_from_content(user_content)
