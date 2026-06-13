"""Cross-database ORDER BY helpers (SQLite rowid vs Postgres columns)."""

from __future__ import annotations

from models import Conversation, File, Message


def messages_oldest_first():
    return Message.created_at.asc()


def messages_recent_first():
    return Message.created_at.desc()


def files_recent_first():
    """Files have no created_at; id is a stable fallback for recency."""
    return File.id.desc()


def conversations_recent_first():
    """Conversations have no created_at; id is a stable fallback."""
    return Conversation.id.desc()
