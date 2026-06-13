from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Message, MessageFeedback, Workspace, User
from schema import MessageFeedbackUpdate, MetricsSummaryOut
from services.metrics import get_metrics_summary

router = APIRouter(tags=["metrics"])

from services.auth.dependencies import get_current_user_for_request
from services.workspace_access import get_accessible_workspace



@router.get(
    "/workspaces/{workspace_id}/metrics/summary",
    response_model=MetricsSummaryOut,
)
async def metrics_summary(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    summary = await get_metrics_summary(workspace_id, db)
    return MetricsSummaryOut(**summary)


@router.post("/messages/{message_id}/feedback", status_code=204)
async def submit_message_feedback(
    message_id: str,
    body: MessageFeedbackUpdate,
    db: AsyncSession = Depends(get_db),
):
    message = await db.get(Message, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != "assistant":
        raise HTTPException(
            status_code=400,
            detail="Feedback is only supported on assistant messages",
        )

    if body.rating not in (1, 5):
        raise HTTPException(status_code=400, detail="rating must be 1 (down) or 5 (up)")

    result = await db.execute(
        select(MessageFeedback).where(MessageFeedback.message_id == message_id)
    )
    feedback = result.scalar_one_or_none()
    if feedback is None:
        feedback = MessageFeedback(message_id=message_id, rating=body.rating)
        db.add(feedback)
    else:
        feedback.rating = body.rating

    await db.commit()
