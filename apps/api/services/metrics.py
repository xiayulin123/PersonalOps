from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import ChatMetric, Conversation, Message, MessageFeedback


async def _feedback_counts(workspace_id: str, db: AsyncSession) -> tuple[int, int]:
    feedback_up_result = await db.execute(
        select(func.count())
        .select_from(MessageFeedback)
        .join(Message, MessageFeedback.message_id == Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.workspace_id == workspace_id,
            MessageFeedback.rating == 5,
        )
    )
    feedback_down_result = await db.execute(
        select(func.count())
        .select_from(MessageFeedback)
        .join(Message, MessageFeedback.message_id == Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.workspace_id == workspace_id,
            MessageFeedback.rating == 1,
        )
    )
    return (
        int(feedback_up_result.scalar_one() or 0),
        int(feedback_down_result.scalar_one() or 0),
    )


async def _empty_summary(workspace_id: str, db: AsyncSession) -> dict:
    feedback_up, feedback_down = await _feedback_counts(workspace_id, db)
    return {
        "total_chats": 0,
        "avg_latency_ms": 0,
        "citation_rate": 0.0,
        "route_breakdown": {},
        "feedback_up": feedback_up,
        "feedback_down": feedback_down,
    }


async def record_chat_metric(
    workspace_id: str,
    result: dict,
    *,
    latency_ms: int,
    db: AsyncSession | None = None,
) -> None:
    if not settings.metrics_enabled:
        return

    metric = ChatMetric(
        workspace_id=workspace_id,
        route=str(result.get("route") or "direct"),
        latency_ms=max(0, int(latency_ms)),
        file_source_count=len(result.get("sources", [])),
        web_source_count=len(result.get("web_sources", [])),
        had_trace=bool(result.get("trace")),
    )

    if db is not None:
        db.add(metric)
        await db.flush()
        return

    from database import SessionLocal

    async with SessionLocal() as session:
        session.add(metric)
        await session.commit()


async def get_metrics_summary(workspace_id: str, db: AsyncSession) -> dict:
    total_result = await db.execute(
        select(func.count())
        .select_from(ChatMetric)
        .where(ChatMetric.workspace_id == workspace_id)
    )
    total_chats = int(total_result.scalar_one() or 0)

    if total_chats == 0:
        return await _empty_summary(workspace_id, db)

    avg_result = await db.execute(
        select(func.avg(ChatMetric.latency_ms)).where(
            ChatMetric.workspace_id == workspace_id
        )
    )
    avg_latency = avg_result.scalar_one()
    avg_latency_ms = int(round(float(avg_latency or 0)))

    cited_result = await db.execute(
        select(func.count())
        .select_from(ChatMetric)
        .where(
            ChatMetric.workspace_id == workspace_id,
            ChatMetric.file_source_count > 0,
        )
    )
    cited_chats = int(cited_result.scalar_one() or 0)
    citation_rate = round(cited_chats / total_chats, 2) if total_chats else 0.0

    route_rows = await db.execute(
        select(ChatMetric.route, func.count())
        .where(ChatMetric.workspace_id == workspace_id)
        .group_by(ChatMetric.route)
    )
    route_breakdown = {route: int(count) for route, count in route_rows.all()}

    feedback_up, feedback_down = await _feedback_counts(workspace_id, db)

    return {
        "total_chats": total_chats,
        "avg_latency_ms": avg_latency_ms,
        "citation_rate": citation_rate,
        "route_breakdown": route_breakdown,
        "feedback_up": feedback_up,
        "feedback_down": feedback_down,
    }
