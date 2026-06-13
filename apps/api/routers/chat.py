import json
import logging
import time
import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal, get_db
from models import Conversation, Message, User, Workspace
from schema import (
    AgentStepOut,
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    ConversationOut,
    SourceOut,
    WebSourceOut,
)
from services.agent.runner import run_agent, run_agent_stream
from services.conversation import (
    create_conversation,
    get_conversation_for_workspace,
    get_latest_conversation,
    list_workspace_conversations,
    load_recent_history,
    load_workspace_chat_messages,
    maybe_update_conversation_title,
)
from services.metrics import record_chat_metric
from services.deployment import assert_chat_mode_allowed
from services.auth.dependencies import get_current_user_for_request
from services.auth.openai_access import http_error_for_missing_openai, openai_context_for_user
from services.openai_runtime import MissingOpenAIKeyError
from services.workspace_access import get_accessible_workspace
from services.personalization.prompt_log import (
    record_user_prompt,
    resolve_workspace_chat_mode,
)
from services.templates import build_template_message, get_template_by_id
from services.storage.conversation_export import export_conversation_after_chat

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


async def _resolve_conversation(
    workspace_id: str,
    conversation_id: str | None,
    db: AsyncSession,
) -> Conversation:
    if conversation_id:
        conversation = await get_conversation_for_workspace(
            conversation_id, workspace_id, db
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation

    conversation = await get_latest_conversation(workspace_id, db)
    if conversation is None:
        conversation = await create_conversation(workspace_id, db)
    return conversation


def _to_chat_response(result: dict) -> ChatResponse:
    return ChatResponse(
        answer=result["answer"],
        sources=[SourceOut(**source) for source in result.get("sources", [])],
        web_sources=[WebSourceOut(**source) for source in result.get("web_sources", [])],
        trace=[AgentStepOut(**step) for step in result.get("trace", [])],
        route=result.get("route"),
        chat_engine=result.get("chat_engine"),
        agent_label=result.get("agent_label"),
        assistant_message_id=result.get("assistant_message_id"),
    )


def _format_sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _prepare_chat(
    workspace_id: str,
    body: ChatRequest,
    db: AsyncSession,
    current_user: User | None,
) -> tuple[Workspace, str, str | None, dict | None, str, Conversation, list]:
    workspace = await get_accessible_workspace(workspace_id, db, current_user)
    assert_chat_mode_allowed(
        await resolve_workspace_chat_mode(db, workspace_id)
    )

    message = body.message.strip()
    template_id = body.template_id

    if not message and not template_id:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    template = get_template_by_id(workspace.type, template_id) if template_id else None
    if template_id and template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    agent_message = (
        build_template_message(template["prompt"], message) if template else message
    )

    conversation = await _resolve_conversation(
        workspace_id, body.conversation_id, db
    )
    history = await load_recent_history(conversation.id, db)

    if template:
        user_content = (
            f"[{template['label']}] {message}".strip()
            if message
            else f"[{template['label']}]"
        )
    else:
        user_content = message

    return (
        workspace,
        agent_message,
        template_id,
        template,
        user_content,
        conversation,
        history,
    )


async def _persist_chat_messages(
    workspace_id: str,
    conversation_id: str,
    user_content: str,
    result: dict,
    template_id: str | None,
    *,
    latency_ms: int,
) -> str:
    assistant_metadata = {
        "sources": result.get("sources", []),
        "web_sources": result.get("web_sources", []),
        "trace": result.get("trace", []),
        "route": result.get("route"),
        "chat_engine": result.get("chat_engine"),
        "agent_label": result.get("agent_label"),
        "template_id": template_id,
    }

    async with SessionLocal() as db:
        chat_mode = await resolve_workspace_chat_mode(db, workspace_id)
        user_message = Message(
            conversation_id=conversation_id, role="user", content=user_content
        )
        db.add(user_message)
        await db.flush()
        await record_user_prompt(
            db,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            message_id=user_message.id,
            content=user_content,
            chat_mode=chat_mode,
        )
        await maybe_update_conversation_title(conversation_id, user_content, db)
        assistant_message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=result["answer"],
            sources_json=json.dumps(assistant_metadata),
        )
        db.add(assistant_message)
        await db.flush()
        assistant_message_id = assistant_message.id
        await record_chat_metric(
            workspace_id,
            result,
            latency_ms=latency_ms,
            db=db,
        )
        await db.commit()

    return assistant_message_id


def _schedule_conversation_export(
    background_tasks: BackgroundTasks,
    *,
    user_id: str | None,
    workspace_id: str,
    conversation_id: str,
) -> None:
    if not user_id:
        return
    background_tasks.add_task(
        export_conversation_after_chat,
        user_id=user_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
    )


def _to_chat_message_out(item: dict) -> ChatMessageOut:
    return ChatMessageOut(
        id=item["id"],
        role=item["role"],
        content=item["content"],
        sources=[SourceOut(**source) for source in item.get("sources", [])],
        web_sources=[
            WebSourceOut(**source) for source in item.get("web_sources", [])
        ],
        trace=[AgentStepOut(**step) for step in item.get("trace", [])],
        route=item.get("route"),
        chat_engine=item.get("chat_engine"),
        agent_label=item.get("agent_label"),
        feedback_rating=item.get("feedback_rating"),
    )


@router.get(
    "/workspaces/{workspace_id}/chat/conversations",
    response_model=list[ConversationOut],
)
async def list_conversations(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    items = await list_workspace_conversations(workspace_id, db)
    return [ConversationOut(**item) for item in items]


@router.post(
    "/workspaces/{workspace_id}/chat/conversations",
    response_model=ConversationOut,
    status_code=201,
)
async def create_chat_conversation(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    conversation = await create_conversation(workspace_id, db)
    await db.commit()
    return ConversationOut(id=conversation.id, title=conversation.title, message_count=0)


@router.get(
    "/workspaces/{workspace_id}/chat/messages",
    response_model=list[ChatMessageOut],
)
async def list_chat_messages(
    workspace_id: str,
    conversation_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    await get_accessible_workspace(workspace_id, db, current_user)
    items = await load_workspace_chat_messages(
        workspace_id,
        db,
        conversation_id=conversation_id,
    )
    return [_to_chat_message_out(item) for item in items]


@router.post("/workspaces/{workspace_id}/chat", response_model=ChatResponse)
async def chat(
    workspace_id: str,
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    (
        _workspace,
        agent_message,
        template_id,
        _template,
        user_content,
        conversation,
        history,
    ) = await _prepare_chat(workspace_id, body, db, current_user)

    started = time.perf_counter()
    try:
        async with openai_context_for_user(db, current_user):
            result = await run_agent(workspace_id, agent_message, history=history)
    except MissingOpenAIKeyError as exc:
        raise http_error_for_missing_openai(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    assistant_message_id = await _persist_chat_messages(
        workspace_id,
        conversation.id,
        user_content,
        result,
        template_id,
        latency_ms=latency_ms,
    )
    result["assistant_message_id"] = assistant_message_id
    _schedule_conversation_export(
        background_tasks,
        user_id=current_user.id if current_user else None,
        workspace_id=workspace_id,
        conversation_id=conversation.id,
    )

    return _to_chat_response(result)


@router.post("/workspaces/{workspace_id}/chat/stream")
async def chat_stream(
    workspace_id: str,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_for_request),
):
    (
        _workspace,
        agent_message,
        template_id,
        _template,
        user_content,
        conversation,
        history,
    ) = await _prepare_chat(workspace_id, body, db, current_user)

    conversation_id = conversation.id
    user_id = current_user.id if current_user else None
    started = time.perf_counter()

    async def event_generator():
        try:
            async with openai_context_for_user(db, current_user):
                async for event in run_agent_stream(
                    workspace_id, agent_message, history=history
                ):
                    if event["type"] == "step":
                        yield _format_sse("step", event["data"])
                    elif event["type"] == "done":
                        result = event["data"]
                        latency_ms = int((time.perf_counter() - started) * 1000)
                        assistant_message_id = await _persist_chat_messages(
                            workspace_id,
                            conversation_id,
                            user_content,
                            result,
                            template_id,
                            latency_ms=latency_ms,
                        )
                        result["assistant_message_id"] = assistant_message_id
                        if user_id:
                            asyncio.create_task(
                                export_conversation_after_chat(
                                    user_id=user_id,
                                    workspace_id=workspace_id,
                                    conversation_id=conversation_id,
                                )
                            )
                        yield _format_sse("done", result)
        except MissingOpenAIKeyError as exc:
            yield _format_sse("error", {"detail": str(exc)})
        except ValueError as exc:
            yield _format_sse("error", {"detail": str(exc)})
        except Exception as exc:
            yield _format_sse("error", {"detail": f"Agent stream failed: {exc}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
