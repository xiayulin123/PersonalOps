from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from cursor_sdk import AgentOptions, LocalAgentOptions
from cursor_sdk.asyncio import AsyncAgent

from config import settings
from services.agent.state import HistoryMessage, MemoryItem
from services.cursor_agent.bridge import get_cursor_client
from services.cursor_agent.labels import derive_agent_label
from services.cursor_agent.prompts import (
    build_cursor_agent_prompt,
    workspace_uploads_dir,
)
from services.cursor_agent.trace import CursorRunCollector
from services.cursor_agent.verify_flow import apply_post_verify

logger = logging.getLogger("personalops.cursor_agent")

StreamEvent = dict[str, Any]


def _effective_chat_mode(workspace) -> str:
    mode = getattr(workspace, "chat_mode", None) or settings.chat_default_mode
    return mode if mode in ("langgraph", "cursor_agent") else "langgraph"


def is_cursor_agent_mode(workspace) -> bool:
    return _effective_chat_mode(workspace) == "cursor_agent"


def _initial_trace(history: list[HistoryMessage]) -> list[dict]:
    trace: list[dict] = []
    if history:
        trace.append(
            {
                "step": 1,
                "label": "Loaded conversation history",
                "detail": f"{len(history)} message(s)",
            }
        )
    return trace


def _build_agent_options(cwd: str) -> AgentOptions:
    return AgentOptions(
        api_key=settings.cursor_api_key,
        model=settings.cursor_agent_model,
        local=LocalAgentOptions(cwd=cwd),
    )


async def _iter_cursor_agent_run(
    workspace,
    question: str,
    memory_items: list[MemoryItem],
    tool_settings: dict,
    history: list[HistoryMessage] | None,
) -> AsyncIterator[tuple[str, Any]]:
    """Yield ('step', trace_dict) during the run, then ('done', collector)."""
    cwd = str(workspace_uploads_dir(workspace.id))
    workspace_uploads_dir(workspace.id).mkdir(parents=True, exist_ok=True)

    prompt = build_cursor_agent_prompt(
        question,
        workspace_id=workspace.id,
        workspace_type=workspace.type,
        memory_items=memory_items,
        tool_settings=tool_settings,
        history=history,
    )

    client = await get_cursor_client()
    collector = CursorRunCollector()
    for step in _initial_trace(history or []):
        collector.trace.append(step)
        yield ("step", step)

    collector.append_trace("Started Cursor Agent (local)", cwd)
    yield ("step", collector.trace[-1])

    agent = await AsyncAgent.create(_build_agent_options(cwd), client=client)
    try:
        run = await agent.send(prompt)
        async for message in run.stream():
            files_before = len(collector.files_read)
            collector.consume_message(message)
            if len(collector.files_read) > files_before:
                newest = sorted(collector.files_read)[-1]
                collector.append_trace("Reading workspace file", newest)
                yield ("step", collector.trace[-1])
        result = await run.wait()
        if result.result and not collector.answer:
            collector.answer_parts.append(result.result)
        if result.status == "error":
            raise RuntimeError(f"Cursor Agent run failed: {result.status}")
    finally:
        await agent.close()

    files_detail = (
        f"{len(collector.files_read)} file(s)"
        if collector.files_read
        else "no files read"
    )
    collector.append_trace("Agent read workspace files", files_detail)
    yield ("step", collector.trace[-1])
    yield ("done", collector)


async def _run_cursor_agent_collect(
    workspace,
    question: str,
    memory_items: list[MemoryItem],
    tool_settings: dict,
    history: list[HistoryMessage] | None,
) -> CursorRunCollector:
    collector: CursorRunCollector | None = None
    async for kind, payload in _iter_cursor_agent_run(
        workspace, question, memory_items, tool_settings, history
    ):
        if kind == "done":
            collector = payload
    if collector is None:
        raise RuntimeError("Cursor Agent run produced no result")
    return collector


async def run_cursor_agent(
    workspace,
    question: str,
    tool_settings: dict,
    memory_items: list[MemoryItem],
    history: list[HistoryMessage] | None = None,
) -> dict:
    trimmed = question.strip()
    if not trimmed:
        return {
            "answer": "Please enter a question.",
            "sources": [],
            "web_sources": [],
            "trace": [],
            "route": "direct",
            "chat_engine": "cursor_agent",
            "agent_label": "direct",
        }

    if not settings.cursor_api_key.strip():
        return {
            "answer": "Cursor Agent is not configured. Set CURSOR_API_KEY on the API server.",
            "sources": [],
            "web_sources": [],
            "trace": [],
            "route": "direct",
            "chat_engine": "cursor_agent",
            "agent_label": "unknown",
        }

    collector = await _run_cursor_agent_collect(
        workspace, trimmed, memory_items, tool_settings, history
    )
    draft = collector.answer or "I could not produce an answer."
    sources = collector.sources_from_files()
    agent_label = derive_agent_label(
        files_read_count=len(collector.files_read),
        web_tool_used=collector.web_tool_used,
        web_sources_count=0,
        question=trimmed,
    )

    verified = await apply_post_verify(
        question=trimmed,
        draft_answer=draft,
        sources=sources,
        web_sources=[],
        tool_settings=tool_settings,
        workspace_type=workspace.type,
        memory_items=memory_items,
        history=history,
        route=agent_label,
        trace=collector.trace,
    )

    final_label = derive_agent_label(
        files_read_count=len(verified["sources"]),
        web_tool_used=collector.web_tool_used,
        web_sources_count=len(verified.get("web_sources", [])),
        question=trimmed,
    )

    return {
        "answer": verified["answer"],
        "sources": verified["sources"],
        "web_sources": verified.get("web_sources", []),
        "trace": verified["trace"],
        "route": final_label,
        "chat_engine": "cursor_agent",
        "agent_label": final_label,
    }


async def run_cursor_agent_stream(
    workspace,
    question: str,
    tool_settings: dict,
    memory_items: list[MemoryItem],
    history: list[HistoryMessage] | None = None,
) -> AsyncIterator[StreamEvent]:
    trimmed = question.strip()
    if not trimmed:
        yield {
            "type": "done",
            "data": {
                "answer": "Please enter a question.",
                "sources": [],
                "web_sources": [],
                "trace": [],
                "route": "direct",
                "chat_engine": "cursor_agent",
                "agent_label": "direct",
            },
        }
        return

    if not settings.cursor_api_key.strip():
        yield {
            "type": "done",
            "data": {
                "answer": "Cursor Agent is not configured. Set CURSOR_API_KEY on the API server.",
                "sources": [],
                "web_sources": [],
                "trace": [],
                "route": "direct",
                "chat_engine": "cursor_agent",
                "agent_label": "unknown",
            },
        }
        return

    collector: CursorRunCollector | None = None
    try:
        async for kind, payload in _iter_cursor_agent_run(
            workspace, trimmed, memory_items, tool_settings, history
        ):
            if kind == "step":
                yield {"type": "step", "data": payload}
            else:
                collector = payload
    except Exception as exc:
        logger.exception("cursor_agent failed workspace_id=%s", workspace.id)
        yield {
            "type": "done",
            "data": {
                "answer": f"Cursor Agent error: {exc}",
                "sources": [],
                "web_sources": [],
                "trace": _initial_trace(history or []),
                "route": "unknown",
                "chat_engine": "cursor_agent",
                "agent_label": "unknown",
            },
        }
        return

    if collector is None:
        yield {
            "type": "done",
            "data": {
                "answer": "Cursor Agent produced no result.",
                "sources": [],
                "web_sources": [],
                "trace": _initial_trace(history or []),
                "route": "unknown",
                "chat_engine": "cursor_agent",
                "agent_label": "unknown",
            },
        }
        return

    draft = collector.answer or "I could not produce an answer."
    sources = collector.sources_from_files()
    agent_label = derive_agent_label(
        files_read_count=len(collector.files_read),
        web_tool_used=collector.web_tool_used,
        web_sources_count=0,
        question=trimmed,
    )

    verified = await apply_post_verify(
        question=trimmed,
        draft_answer=draft,
        sources=sources,
        web_sources=[],
        tool_settings=tool_settings,
        workspace_type=workspace.type,
        memory_items=memory_items,
        history=history,
        route=agent_label,
        trace=collector.trace,
    )

    emitted = len(collector.trace)
    for step in verified["trace"][emitted:]:
        yield {"type": "step", "data": step}

    final_label = derive_agent_label(
        files_read_count=len(verified["sources"]),
        web_tool_used=collector.web_tool_used,
        web_sources_count=len(verified.get("web_sources", [])),
        question=trimmed,
    )

    yield {
        "type": "done",
        "data": {
            "answer": verified["answer"],
            "sources": verified["sources"],
            "web_sources": verified.get("web_sources", []),
            "trace": verified["trace"],
            "route": final_label,
            "chat_engine": "cursor_agent",
            "agent_label": final_label,
        },
    }
