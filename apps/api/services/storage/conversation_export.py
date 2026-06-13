"""Mirror conversations to GCS JSONL (Plan B B4)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from database import SessionLocal
from models import Conversation, Message, Workspace
from services.db_ordering import messages_oldest_first
from services.storage import gcs_app_storage as gcs

logger = logging.getLogger(__name__)


def should_export_conversations(*, user_id: str | None) -> bool:
    return gcs.is_gcs_app_storage_enabled() and bool(user_id)


def _serialize_conversation(conversation: Conversation, messages: list[Message]) -> bytes:
    lines: list[str] = []
    lines.append(
        json.dumps(
            {
                "type": "meta",
                "conversation_id": conversation.id,
                "workspace_id": conversation.workspace_id,
                "title": conversation.title,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "message_count": len(messages),
            },
            ensure_ascii=False,
        )
    )
    for message in messages:
        metadata: dict | list | None = None
        if message.sources_json:
            try:
                metadata = json.loads(message.sources_json)
            except json.JSONDecodeError:
                metadata = None
        lines.append(
            json.dumps(
                {
                    "type": "message",
                    "id": message.id,
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at.isoformat()
                    if message.created_at
                    else None,
                    "metadata": metadata,
                },
                ensure_ascii=False,
            )
        )
    payload = "\n".join(lines)
    if lines:
        payload += "\n"
    return payload.encode("utf-8")


async def export_conversation_to_gcs(
    *,
    user_id: str,
    workspace_id: str,
    conversation_id: str,
) -> str | None:
    """Export full conversation to GCS; returns gs:// URI or None if skipped."""
    if not should_export_conversations(user_id=user_id):
        return None

    async with SessionLocal() as db:
        conversation = await db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
            )
        )
        if conversation is None:
            return None

        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(messages_oldest_first())
        )
        messages = list(result.scalars().all())
        payload = _serialize_conversation(conversation, messages)

    try:
        gcs_uri = gcs.export_conversation_jsonl(
            user_id=user_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            content=payload,
        )
    except Exception:
        logger.exception(
            "Failed to export conversation %s to GCS", conversation_id
        )
        return None

    async with SessionLocal() as db:
        row = await db.get(Conversation, conversation_id)
        if row is not None:
            row.gcs_export_uri = gcs_uri
            row.gcs_exported_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()

    return gcs_uri


async def export_conversation_after_chat(
    *,
    user_id: str | None,
    workspace_id: str,
    conversation_id: str,
) -> None:
    if not user_id:
        return
    await export_conversation_to_gcs(
        user_id=user_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
    )


def parse_conversation_export_payload(payload: bytes) -> tuple[dict, list[dict]]:
    meta: dict | None = None
    messages: list[dict] = []
    for line in payload.decode("utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("type") == "meta":
            meta = row
        elif row.get("type") == "message":
            messages.append(row)
    if meta is None:
        raise ValueError("Conversation export missing meta line")
    return meta, messages


def _parse_exported_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


async def restore_conversation_from_gcs_export(
    *,
    user_id: str,
    gcs_uri: str,
    dry_run: bool = False,
) -> str:
    """Restore one conversation from GCS JSONL. Returns restored|skipped|failed."""
    try:
        payload = gcs.download_blob_bytes(gcs_uri)
        meta, exported_messages = parse_conversation_export_payload(payload)
    except Exception:
        logger.exception("Failed to read export %s", gcs_uri)
        return "failed"

    conversation_id = str(meta.get("conversation_id") or "")
    workspace_id = str(meta.get("workspace_id") or "")
    if not conversation_id or not workspace_id:
        return "failed"

    async with SessionLocal() as db:
        workspace = await db.scalar(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.user_id == user_id,
            )
        )
        if workspace is None:
            logger.warning(
                "Skip restore %s — workspace %s not owned by user %s",
                gcs_uri,
                workspace_id,
                user_id,
            )
            return "skipped"

        existing = await db.get(Conversation, conversation_id)
        if existing is not None:
            message_count = await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.conversation_id == conversation_id)
            )
            if message_count and message_count > 0:
                return "skipped"

        if dry_run:
            return "restored"

        exported_at = _parse_exported_at(meta.get("exported_at"))
        if existing is None:
            db.add(
                Conversation(
                    id=conversation_id,
                    workspace_id=workspace_id,
                    title=meta.get("title") or "New Chat",
                    gcs_export_uri=gcs_uri,
                    gcs_exported_at=exported_at,
                )
            )
        else:
            existing.gcs_export_uri = gcs_uri
            existing.gcs_exported_at = exported_at
            await db.execute(
                delete(Message).where(Message.conversation_id == conversation_id)
            )

        for item in exported_messages:
            role = item.get("role")
            content = item.get("content")
            if role not in ("user", "assistant") or not content:
                continue
            metadata = item.get("metadata")
            sources_json = (
                json.dumps(metadata, ensure_ascii=False)
                if metadata is not None
                else None
            )
            message_kwargs: dict = {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "sources_json": sources_json,
            }
            if item.get("id"):
                message_kwargs["id"] = item["id"]
            created_at = _parse_exported_at(item.get("created_at"))
            if created_at is not None:
                message_kwargs["created_at"] = created_at
            db.add(Message(**message_kwargs))

        await db.commit()

    return "restored"


async def restore_user_conversations_from_gcs(
    *,
    user_id: str,
    workspace_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Restore missing/empty conversations from GCS exports for one user."""
    counts = {"restored": 0, "skipped": 0, "failed": 0}
    if not gcs.is_gcs_app_storage_enabled():
        return counts

    try:
        exports = gcs.iter_conversation_export_objects(
            user_id,
            workspace_id=workspace_id,
        )
    except Exception:
        logger.exception("Failed to list conversation exports for user %s", user_id)
        counts["failed"] += 1
        return counts

    for export in exports:
        status = await restore_conversation_from_gcs_export(
            user_id=user_id,
            gcs_uri=export["gcs_uri"],
            dry_run=dry_run,
        )
        counts[status] = counts.get(status, 0) + 1

    return counts
