from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select

from database import SessionLocal
from models import LifeGoogleConnection, LifeInboxBrief
from services.life.google_client import (
    ensure_valid_google_token,
    fetch_gmail_messages,
    parse_gmail_message,
)

logger = logging.getLogger(__name__)


async def sync_workspace_gmail(workspace_id: str) -> int:
    async with SessionLocal() as db:
        connection = await db.get(LifeGoogleConnection, workspace_id)
        if connection is None or not connection.enabled or not connection.refresh_token:
            return 0

        try:
            token = await ensure_valid_google_token(connection, db)
            messages = await fetch_gmail_messages(token, max_results=50)
        except Exception as exc:
            logger.warning("Gmail sync failed workspace=%s: %s", workspace_id, exc)
            return 0

        existing = await db.execute(
            select(LifeInboxBrief).where(
                LifeInboxBrief.workspace_id == workspace_id,
                LifeInboxBrief.provider == "google",
            )
        )
        known_by_id = {
            brief.graph_message_id: brief for brief in existing.scalars().all()
        }
        created = 0

        for raw in messages:
            parsed = parse_gmail_message(raw)
            graph_id = parsed.get("id")
            if not graph_id:
                continue

            if graph_id in known_by_id:
                brief = known_by_id[graph_id]
                brief.received_at = parsed["received_at"]
                brief.from_address = (parsed.get("from_address") or "unknown")[:255]
                brief.from_name = (parsed.get("from_name") or "")[:255] or None
                brief.subject = parsed["subject"][:512]
                brief.body_preview = (parsed.get("body_preview") or "")[:4000]
                continue

            is_unread = parsed.get("is_unread", False)
            subject = parsed["subject"]
            from_name = parsed.get("from_name")
            from_address = parsed.get("from_address") or "unknown"
            body_preview = parsed.get("body_preview") or ""
            received_at = parsed["received_at"]

            if is_unread:
                summary = body_preview[:4000] or subject
                engine = "pending"
            else:
                summary = body_preview[:4000] or subject
                engine = "raw"

            db.add(
                LifeInboxBrief(
                    workspace_id=workspace_id,
                    provider="google",
                    graph_message_id=graph_id,
                    subject=subject[:512],
                    from_address=from_address[:255],
                    from_name=(from_name or "")[:255] or None,
                    received_at=received_at,
                    body_preview=body_preview[:4000],
                    summary=summary,
                    summary_engine=engine,
                    dismissed=False,
                )
            )
            if is_unread:
                created += 1

        connection.last_mail_sync_at = datetime.utcnow()
        await db.commit()
        return created
