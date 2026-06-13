"""One-off: copy existing user messages into prompt_log for archive testing."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from database import SessionLocal
from models import Conversation, Message, PromptLog
from services.personalization.redact import redact_secrets


async def main() -> None:
    async with SessionLocal() as db:
        result = await db.execute(
            select(Message, Conversation.workspace_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Message.role == "user")
            .order_by(Message.created_at.asc())
        )
        existing = {
            r
            for r in (await db.execute(select(PromptLog.message_id))).scalars().all()
            if r
        }
        added = 0
        for msg, workspace_id in result.all():
            if msg.id in existing:
                continue
            text = (msg.content or "").strip()
            if not text:
                continue
            db.add(
                PromptLog(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    conversation_id=msg.conversation_id,
                    message_id=msg.id,
                    role="user",
                    content=text,
                    content_redacted=redact_secrets(text),
                    chat_mode="langgraph",
                    char_count=len(text),
                    created_at=msg.created_at,
                )
            )
            added += 1
        await db.commit()
        print(f"Backfilled {added} prompt_log rows")


if __name__ == "__main__":
    asyncio.run(main())
