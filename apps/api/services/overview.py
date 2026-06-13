from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Conversation, File, Memory, Message, Workspace
from routers.tools import _parse_tool_settings
from services.db_ordering import files_recent_first, messages_recent_first
from services.templates import get_templates

_PREVIEW_MAX = 160
_RECENT_FILES = 5
_RECENT_MESSAGES = 3
_SUGGESTED_TEMPLATES = 3


def _preview(content: str, max_len: int = _PREVIEW_MAX) -> str:
    trimmed = content.strip().replace("\n", " ")
    if len(trimmed) <= max_len:
        return trimmed
    return f"{trimmed[:max_len]}..."


async def build_workspace_overview(
    workspace: Workspace,
    db: AsyncSession,
) -> dict:
    file_result = await db.execute(
        select(File)
        .where(File.workspace_id == workspace.id)
        .order_by(files_recent_first())
        .limit(_RECENT_FILES)
    )
    recent_files = [
        {
            "filename": file_record.filename,
            "status": file_record.status,
            "chunk_count": file_record.chunk_count,
            "uploaded_at": None,
        }
        for file_record in file_result.scalars().all()
    ]

    status_result = await db.execute(
        select(File.status, func.count())
        .where(File.workspace_id == workspace.id)
        .group_by(File.status)
    )
    status_counts = {status: count for status, count in status_result.all()}
    indexing_summary = {
        "ready": int(status_counts.get("ready", 0)),
        "failed": int(status_counts.get("failed", 0)),
        "needs_ocr": int(status_counts.get("needs_ocr", 0)),
        "pending": int(status_counts.get("pending", 0)),
        "indexing": int(status_counts.get("indexing", 0)),
        "ocr": int(status_counts.get("ocr", 0)),
        "empty": int(status_counts.get("empty", 0)),
        "total": int(sum(status_counts.values())),
    }

    memory_count = int(
        await db.scalar(
            select(func.count())
            .select_from(Memory)
            .where(Memory.workspace_id == workspace.id)
        )
        or 0
    )

    conversation_ids = (
        await db.scalars(
            select(Conversation.id).where(Conversation.workspace_id == workspace.id)
        )
    ).all()

    recent_messages: list[dict] = []
    if conversation_ids:
        message_result = await db.execute(
            select(Message)
            .where(Message.conversation_id.in_(conversation_ids))
            .order_by(messages_recent_first())
            .limit(_RECENT_MESSAGES)
        )
        recent_messages = [
            {
                "role": message.role,
                "content_preview": _preview(message.content),
                "created_at": None,
            }
            for message in reversed(message_result.scalars().all())
        ]

    templates = get_templates(workspace.type)[:_SUGGESTED_TEMPLATES]
    suggested_templates = [
        {
            "id": template["id"],
            "label": template["label"],
            "description": template["description"],
        }
        for template in templates
    ]

    tool_settings = _parse_tool_settings(workspace.tool_settings_json)

    return {
        "recent_files": recent_files,
        "recent_messages": recent_messages,
        "memory_count": memory_count,
        "tool_settings": tool_settings,
        "indexing_summary": indexing_summary,
        "suggested_templates": suggested_templates,
    }
