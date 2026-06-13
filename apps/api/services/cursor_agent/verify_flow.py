from __future__ import annotations

from config import settings
from services.agent.prompts import (
    GENERATOR_REVISE_USER_MESSAGE,
    GENERATOR_WEB_REVISE_USER_MESSAGE,
    INSUFFICIENT_LOCAL_EVIDENCE_ANSWER,
    VERIFIER_SYSTEM_PROMPT,
    augment_question_with_history,
    build_generator_messages,
    build_verifier_user_prompt,
    resolve_verify_failure_action,
)
from services.agent.state import HistoryMessage, MemoryItem
from services.indexer import _openai_client
from services.web_search import search_web


def _chat(system: str, user: str, temperature: float = 0.2) -> str:
    response = _openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return (response.choices[0].message.content or "").strip()


def _chat_messages(messages: list[dict], temperature: float = 0.2) -> str:
    response = _openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=temperature,
    )
    return (response.choices[0].message.content or "").strip()


async def apply_post_verify(
    *,
    question: str,
    draft_answer: str,
    sources: list[dict],
    web_sources: list[dict],
    tool_settings: dict,
    workspace_type: str,
    memory_items: list[MemoryItem],
    history: list[HistoryMessage] | None,
    route: str,
    trace: list[dict],
) -> dict:
    """Verify draft and optionally revise / web-fallback. Returns updated fields."""
    trace = list(trace)
    if not settings.openai_api_key.strip():
        trace.append(
            {
                "step": len(trace) + 1,
                "label": "Skipped verify",
                "detail": "OPENAI_API_KEY not set — using Cursor draft as-is",
            }
        )
        return {
            "answer": draft_answer,
            "sources": sources,
            "web_sources": web_sources,
            "trace": trace,
            "route": route,
        }

    verdict = _chat(
        VERIFIER_SYSTEM_PROMPT,
        build_verifier_user_prompt(
            question,
            draft_answer,
            route,
            sources,
            web_sources,
        ),
        temperature=0.0,
    )
    cleaned = verdict.strip().lower()
    result = "pass" if cleaned == "pass" else "revise"
    trace.append(
        {
            "step": len(trace) + 1,
            "label": "Verified answer",
            "detail": result,
        }
    )

    if result == "pass":
        return {
            "answer": draft_answer,
            "sources": sources,
            "web_sources": web_sources,
            "trace": trace,
            "route": route,
        }

    action = resolve_verify_failure_action(
        retrieved_sources=sources,
        web_sources=web_sources,
        tool_settings=tool_settings,
    )

    memory = memory_items if tool_settings.get("memory", True) else []

    if action == "insufficient":
        trace.append(
            {
                "step": len(trace) + 1,
                "label": "Insufficient local evidence",
                "detail": "web_search disabled",
            }
        )
        return {
            "answer": INSUFFICIENT_LOCAL_EVIDENCE_ANSWER,
            "sources": sources,
            "web_sources": [],
            "trace": trace,
            "route": "insufficient",
        }

    if action in ("fallback_web", "revise_web"):
        updated_web = list(web_sources)
        if action == "fallback_web":
            search_query = augment_question_with_history(question, history or [])
            if len(search_query) > 500:
                search_query = search_query[:500]
            updated_web = search_web(search_query, max_results=5)
            trace.append(
                {
                    "step": len(trace) + 1,
                    "label": "Searched the web after local miss",
                    "detail": f"{len(updated_web)} result(s)",
                }
            )

        revise_messages = build_generator_messages(
            question,
            workspace_type,
            memory,
            "",
            updated_web,
            "web_search",
            history,
        )
        revise_messages.append(
            {"role": "user", "content": GENERATOR_WEB_REVISE_USER_MESSAGE}
        )
        revised = _chat_messages(revise_messages, temperature=0.1)
        trace.append(
            {
                "step": len(trace) + 1,
                "label": "Revised answer from web",
                "detail": None,
            }
        )
        return {
            "answer": revised,
            "sources": sources,
            "web_sources": updated_web,
            "trace": trace,
            "route": "web_search",
        }

    context_block = _sources_to_context(sources)
    revise_messages = build_generator_messages(
        question,
        workspace_type,
        memory,
        context_block,
        [],
        "file_rag",
        history,
    )
    revise_messages.append(
        {"role": "user", "content": GENERATOR_REVISE_USER_MESSAGE}
    )
    revised = _chat_messages(revise_messages, temperature=0.1)
    trace.append(
        {
            "step": len(trace) + 1,
            "label": "Revised answer from files",
            "detail": None,
        }
    )
    return {
        "answer": revised,
        "sources": sources,
        "web_sources": [],
        "trace": trace,
        "route": "file_rag",
    }


def _sources_to_context(sources: list[dict]) -> str:
    if not sources:
        return ""
    blocks: list[str] = []
    for index, source in enumerate(sources, start=1):
        filename = source.get("filename", "file")
        page = source.get("page", 1)
        snippet = source.get("snippet", "")
        blocks.append(f"[{index}] {filename} (p.{page})\n{snippet}")
    return "\n\n".join(blocks)
