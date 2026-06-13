from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from database import SessionLocal
from models import LifeInboxBrief, LifeOutlookConnection
from services.life.outlook_graph import (
    ensure_valid_token,
    fetch_inbox_messages,
    parse_graph_datetime,
)

logger = logging.getLogger(__name__)


async def sync_workspace_mail(workspace_id: str) -> int:
    """Fetch new inbox messages and create briefs. Returns count of new briefs."""
    async with SessionLocal() as db:
        connection = await db.get(LifeOutlookConnection, workspace_id)
        if connection is None or not connection.enabled or not connection.refresh_token:
            return 0

        try:
            token = await ensure_valid_token(connection, db)
            messages = await fetch_inbox_messages(token, top=50)
        except Exception as exc:
            logger.warning("Mail sync failed workspace=%s: %s", workspace_id, exc)
            return 0

        existing = await db.execute(
            select(LifeInboxBrief.graph_message_id).where(
                LifeInboxBrief.workspace_id == workspace_id
            )
        )
        known_ids = {row[0] for row in existing.all()}
        created = 0

        for message in messages:
            graph_id = message.get("id")
            if not graph_id or graph_id in known_ids:
                continue

            from_obj = message.get("from", {}).get("emailAddress", {})
            from_address = from_obj.get("address") or "unknown"
            from_name = from_obj.get("name")
            subject = message.get("subject") or "(no subject)"
            body_preview = message.get("bodyPreview") or ""
            received_at = parse_graph_datetime(message.get("receivedDateTime"))
            is_unread = not message.get("isRead")

            if is_unread:
                summary = body_preview[:4000] or subject
                engine = "pending"
            else:
                summary = body_preview[:4000] or subject
                engine = "raw"

            db.add(
                LifeInboxBrief(
                    workspace_id=workspace_id,
                    provider="microsoft",
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
            known_ids.add(graph_id)
            if is_unread:
                created += 1

        connection.last_mail_sync_at = datetime.utcnow()
        await db.commit()
        return created
