from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger("personalops.agent")

from sqlalchemy import select

from database import SessionLocal
from models import File, Workspace
from routers.tools import _parse_tool_settings
from services.agent.graph import get_agent_graph
from services.agent.state import AgentState, HistoryMessage, MemoryItem
from services.cursor_agent.runner import (
    is_cursor_agent_mode,
    run_cursor_agent,
    run_cursor_agent_stream,
)

StreamEvent = dict[str, Any]


async def _load_agent_context(
    workspace_id: str,
) -> tuple[Workspace, dict, list[MemoryItem], list[dict]]:
    async with SessionLocal() as db:
        workspace = await db.get(Workspace, workspace_id)
        if workspace is None:
            raise ValueError("Workspace not found")

        tool_settings = _parse_tool_settings(workspace.tool_settings_json)

        memory_items: list[MemoryItem] = []
        if tool_settings.get("memory", True):
            from services.personalization.memory_load import load_active_memory_items

            memory_items = await load_active_memory_items(db, workspace_id)

        file_result = await db.execute(
            select(File)
            .where(
                File.workspace_id == workspace_id,
                File.status == "ready",
                File.chunk_count > 0,
            )
            .order_by(File.filename.asc())
        )
        indexed_files = [
            {"filename": file_record.filename, "chunk_count": file_record.chunk_count}
            for file_record in file_result.scalars().all()
        ]

    return workspace, tool_settings, memory_items, indexed_files


def _build_initial_state(
    workspace: Workspace,
    question: str,
    tool_settings: dict,
    memory_items: list[MemoryItem],
    indexed_files: list[dict],
    history: list[HistoryMessage] | None = None,
) -> AgentState:
    conversation_history = history or []
    initial_trace: list[dict] = []
    if conversation_history:
        initial_trace.append(
            {
                "step": 1,
                "label": "Loaded conversation history",
                "detail": f"{len(conversation_history)} message(s)",
            }
        )

    return {
        "workspace_id": workspace.id,
        "workspace_type": workspace.type,
        "question": question.strip(),
        "history": conversation_history,
        "tool_settings": tool_settings,
        "memory_items": memory_items,
        "indexed_files": indexed_files,
        "trace": initial_trace,
        "retrieved_sources": [],
        "web_sources": [],
        "context_block": "",
        "answer": "",
    }


def _result_from_state(state: AgentState) -> dict:
    return {
        "answer": state.get("answer", ""),
        "sources": state.get("retrieved_sources", []),
        "web_sources": state.get("web_sources", []),
        "trace": state.get("trace", []),
        "route": state.get("route"),
        "chat_engine": "langgraph",
        "agent_label": None,
    }


async def run_agent(
    workspace_id: str,
    question: str,
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
        }

    workspace, tool_settings, memory_items, indexed_files = await _load_agent_context(
        workspace_id
    )

    logger.info(
        "agent_run workspace_id=%s chat_mode=%s workspace_type=%s history_messages=%d question_chars=%d",
        workspace.id,
        getattr(workspace, "chat_mode", "langgraph"),
        workspace.type,
        len(history or []),
        len(trimmed),
    )

    if is_cursor_agent_mode(workspace):
        result = await run_cursor_agent(
            workspace,
            trimmed,
            tool_settings,
            memory_items,
            history,
        )
        logger.info(
            "agent_done workspace_id=%s engine=cursor_agent label=%s file_sources=%d web_results=%d trace_steps=%d",
            workspace.id,
            result.get("agent_label"),
            len(result.get("sources", [])),
            len(result.get("web_sources", [])),
            len(result.get("trace", [])),
        )
        return result

    initial_state = _build_initial_state(
        workspace,
        trimmed,
        tool_settings,
        memory_items,
        indexed_files,
        history,
    )

    graph = get_agent_graph()
    final_state = await graph.ainvoke(initial_state)
    result = _result_from_state(final_state)
    logger.info(
        "agent_done workspace_id=%s route=%s file_chunks=%d web_results=%d trace_steps=%d",
        workspace.id,
        result.get("route"),
        len(result.get("sources", [])),
        len(result.get("web_sources", [])),
        len(result.get("trace", [])),
    )
    return result


async def run_agent_stream(
    workspace_id: str,
    question: str,
    history: list[HistoryMessage] | None = None,
) -> AsyncIterator[StreamEvent]:
    """Yield trace steps as nodes complete, then a final done payload."""
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
            },
        }
        return

    workspace, tool_settings, memory_items, indexed_files = await _load_agent_context(
        workspace_id
    )

    logger.info(
        "agent_run workspace_id=%s chat_mode=%s workspace_type=%s history_messages=%d question_chars=%d",
        workspace.id,
        getattr(workspace, "chat_mode", "langgraph"),
        workspace.type,
        len(history or []),
        len(trimmed),
    )

    if is_cursor_agent_mode(workspace):
        async for event in run_cursor_agent_stream(
            workspace,
            trimmed,
            tool_settings,
            memory_items,
            history,
        ):
            yield event
        return

    initial_state = _build_initial_state(
        workspace,
        trimmed,
        tool_settings,
        memory_items,
        indexed_files,
        history,
    )

    emitted_trace_count = 0
    for step in initial_state.get("trace", []):
        emitted_trace_count += 1
        yield {"type": "step", "data": step}

    graph = get_agent_graph()
    merged_state: AgentState = dict(initial_state)

    async for update in graph.astream(initial_state, stream_mode="updates"):
        for node_output in update.values():
            if not isinstance(node_output, dict):
                continue

            merged_state.update(node_output)

            trace = node_output.get("trace")
            if isinstance(trace, list):
                while emitted_trace_count < len(trace):
                    yield {"type": "step", "data": trace[emitted_trace_count]}
                    emitted_trace_count += 1

    result = _result_from_state(merged_state)
    logger.info(
        "agent_done workspace_id=%s engine=langgraph route=%s file_chunks=%d web_results=%d trace_steps=%d",
        workspace.id,
        result.get("route"),
        len(result.get("sources", [])),
        len(result.get("web_sources", [])),
        len(result.get("trace", [])),
    )
    yield {"type": "done", "data": result}
