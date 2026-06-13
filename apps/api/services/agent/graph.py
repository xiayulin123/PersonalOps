from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from services.agent.prompts import (
    ROUTER_SYSTEM_PROMPT,
    VERIFIER_SYSTEM_PROMPT,
    augment_question_with_history,
    GENERATOR_REVISE_USER_MESSAGE,
    GENERATOR_WEB_REVISE_USER_MESSAGE,
    INSUFFICIENT_LOCAL_EVIDENCE_ANSWER,
    build_generator_messages,
    build_router_user_prompt,
    build_verifier_user_prompt,
    normalize_route,
    resolve_verify_failure_action,
    should_skip_web_after_retrieve,
)
from services.code_search import (
    extract_code_search_terms,
    search_code,
    should_run_code_search,
)
from services.rag import expand_retrieval_query
from services.agent.logging_utils import log_agent_node
from services.agent.state import AgentState, Route
from services.indexer import _openai_client
from services.rag import _build_context_block, merge_code_search_hits, retrieve_chunks
from services.web_search import search_web

_agent_graph = None


def _append_trace(state: AgentState, label: str, detail: str | None = None) -> list[dict]:
    trace = list(state.get("trace", []))
    trace.append({"step": len(trace) + 1, "label": label, "detail": detail})
    return trace


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


async def classify_node(state: AgentState) -> dict:
    tool_settings = state.get("tool_settings", {})
    history = state.get("history", [])
    routing_question = augment_question_with_history(state["question"], history)
    raw_route = _chat(
        ROUTER_SYSTEM_PROMPT,
        build_router_user_prompt(
            routing_question,
            state.get("workspace_type", "study"),
            tool_settings,
            state.get("indexed_files", []),
            history,
        ),
        temperature=0.0,
    )
    indexed_files = state.get("indexed_files", [])
    route = normalize_route(
        raw_route,
        tool_settings,
        state["question"],
        indexed_files_count=len(indexed_files),
        history=history,
    )
    updates = {
        "route": route,
        "trace": _append_trace(state, "Classified request", route),
    }
    log_agent_node("classify", {**state, **updates}, raw_route=raw_route.strip())
    return updates


async def load_memory_node(state: AgentState) -> dict:
    tool_settings = state.get("tool_settings", {})
    memory_items = state.get("memory_items", [])

    if not tool_settings.get("memory", True):
        memory_items = []

    detail = f"{len(memory_items)} item(s)" if memory_items else "none"
    updates = {
        "memory_items": memory_items,
        "trace": _append_trace(state, "Loaded workspace memory", detail),
    }
    log_agent_node("load_memory", state, memory_items=len(memory_items))
    return updates


async def retrieve_node(state: AgentState) -> dict:
    tool_settings = state.get("tool_settings", {})
    route = state.get("route", "file_rag")

    if not tool_settings.get("file_search", True):
        updates = {
            "trace": _append_trace(state, "Skipped file retrieval", "file_search disabled"),
        }
        log_agent_node("retrieve", state, skipped="file_search_disabled")
        return updates

    if route not in ("file_rag", "hybrid"):
        log_agent_node("retrieve", state, skipped=f"route={route}")
        return {}

    history = state.get("history", [])
    question = augment_question_with_history(state["question"], history)
    retrieval_query = expand_retrieval_query(question)
    n_results = 12 if "主角" in question or "主人公" in question else 10
    retrieved = await retrieve_chunks(
        state["workspace_id"], retrieval_query, n_results=n_results
    )
    documents = retrieved["documents"]
    metadatas = retrieved["metadatas"]
    sources = retrieved["sources"]

    context_block = _build_context_block(documents, metadatas) if documents else ""
    detail = f"{len(sources)} chunk(s)" if sources else "no matches"
    trace = _append_trace(state, "Retrieved workspace files", detail)

    updates: dict = {
        "context_block": context_block,
        "retrieved_sources": sources,
        "retrieved_documents": documents,
        "retrieved_metadatas": metadatas,
        "trace": trace,
    }

    indexed_files = state.get("indexed_files", [])
    if should_skip_web_after_retrieve(
        state["question"],
        route,
        len(sources),
        len(indexed_files),
    ):
        if route == "hybrid":
            updates["route"] = "file_rag"
            updates["trace"] = _append_trace(
                {**state, "trace": trace},
                "Skipped web search",
                "local files sufficient",
            )

    log_agent_node(
        "retrieve",
        {**state, **updates},
        file_chunks=len(updates.get("retrieved_sources", [])),
    )
    return updates


def _should_run_code_search(state: AgentState) -> bool:
    if state.get("workspace_type") != "code":
        return False
    if not state.get("tool_settings", {}).get("code_search", False):
        return False
    if state.get("route", "file_rag") not in ("file_rag", "hybrid"):
        return False

    history = state.get("history", [])
    question = augment_question_with_history(state["question"], history)
    return should_run_code_search(question)


async def code_search_node(state: AgentState) -> dict:
    if not _should_run_code_search(state):
        detail = "code_search disabled" if state.get("workspace_type") == "code" else "not a code workspace"
        if state.get("workspace_type") == "code" and state.get("tool_settings", {}).get("code_search"):
            history = state.get("history", [])
            question = augment_question_with_history(state["question"], history)
            if not should_run_code_search(question):
                detail = "not a code lookup query"
        updates = {
            "trace": _append_trace(state, "Skipped code search", detail),
        }
        log_agent_node("code_search", state, skipped=detail)
        return updates

    history = state.get("history", [])
    question = augment_question_with_history(state["question"], history)
    terms = extract_code_search_terms(question)
    if not terms:
        terms = [state["question"].strip()]

    hits: list[dict] = []
    seen_hit: set[str] = set()
    for term in terms[:3]:
        for hit in search_code(state["workspace_id"], term, max_results=10):
            key = f"{hit.get('filename')}:{hit.get('line_number')}"
            if key in seen_hit:
                continue
            seen_hit.add(key)
            hits.append(hit)
        if len(hits) >= 20:
            break

    if not hits:
        updates = {
            "trace": _append_trace(state, "Code keyword search", "no matches"),
        }
        log_agent_node("code_search", state, code_hits=0)
        return updates

    documents = list(state.get("retrieved_documents", []))
    metadatas = list(state.get("retrieved_metadatas", []))
    sources = list(state.get("retrieved_sources", []))

    documents, metadatas, sources, context_block = merge_code_search_hits(
        documents,
        metadatas,
        sources,
        hits,
        max_total=15,
    )

    detail = f"{len(hits)} line match(es)"
    updates = {
        "context_block": context_block,
        "retrieved_sources": sources,
        "retrieved_documents": documents,
        "retrieved_metadatas": metadatas,
        "trace": _append_trace(state, "Code keyword search", detail),
    }
    log_agent_node(
        "code_search",
        {**state, **updates},
        code_hits=len(hits),
        file_chunks=len(sources),
    )
    return updates


async def web_search_node(state: AgentState) -> dict:
    tool_settings = state.get("tool_settings", {})
    route = state.get("route", "web_search")

    if not tool_settings.get("web_search", False):
        updates = {
            "trace": _append_trace(state, "Skipped web search", "web_search disabled"),
        }
        log_agent_node("web_search", state, skipped="web_search_disabled")
        return updates

    if route not in ("web_search", "hybrid"):
        log_agent_node("web_search", state, skipped=f"route={route}")
        return {}

    history = state.get("history", [])
    search_query = augment_question_with_history(state["question"], history)
    if len(search_query) > 500:
        search_query = search_query[:500]

    results = search_web(search_query, max_results=5)
    detail = f"{len(results)} result(s)" if results else "no results"

    updates = {
        "web_sources": results,
        "trace": _append_trace(state, "Searched the web", detail),
    }
    log_agent_node(
        "web_search",
        {**state, **updates},
        web_results=len(results),
        search_query_chars=len(search_query),
        augmented=search_query != state["question"].strip(),
    )
    return updates


async def generate_node(state: AgentState) -> dict:
    route = state.get("route", "file_rag")
    memory_items = state.get("memory_items", [])
    if not state.get("tool_settings", {}).get("memory", True):
        memory_items = []

    messages = build_generator_messages(
        state["question"],
        state.get("workspace_type", "study"),
        memory_items,
        state.get("context_block", ""),
        state.get("web_sources", []),
        route,
        state.get("history", []),
    )
    answer = _chat_messages(messages)

    updates = {
        "answer": answer,
        "trace": _append_trace(state, "Generated answer"),
    }
    log_agent_node(
        "generate",
        {**state, **updates},
        answer_chars=len(answer),
        file_chunks=len(state.get("retrieved_sources", [])),
        web_results=len(state.get("web_sources", [])),
    )
    return updates


async def verify_node(state: AgentState) -> dict:
    route = state.get("route", "file_rag")
    answer = state.get("answer", "")
    retrieved_sources = state.get("retrieved_sources", [])
    web_sources = list(state.get("web_sources", []))
    verdict = _chat(
        VERIFIER_SYSTEM_PROMPT,
        build_verifier_user_prompt(
            state["question"],
            answer,
            route,
            retrieved_sources,
            web_sources,
        ),
        temperature=0.0,
    )
    cleaned = verdict.strip().lower()
    result = "pass" if cleaned == "pass" else "revise"
    trace = _append_trace(state, "Verified answer", result)

    if result != "revise":
        log_agent_node("verify", state, verdict=result)
        return {"trace": trace}

    tool_settings = state.get("tool_settings", {})
    action = resolve_verify_failure_action(
        retrieved_sources=retrieved_sources,
        web_sources=web_sources,
        tool_settings=tool_settings,
        answer=answer,
    )

    if action == "insufficient":
        updates = {
            "answer": INSUFFICIENT_LOCAL_EVIDENCE_ANSWER,
            "web_sources": [],
            "trace": _append_trace(
                {**state, "trace": trace},
                "Insufficient local evidence",
                "web_search disabled",
            ),
        }
        log_agent_node(
            "verify",
            {**state, **updates},
            verdict="insufficient",
            answer_chars=len(INSUFFICIENT_LOCAL_EVIDENCE_ANSWER),
        )
        return updates

    memory_items = state.get("memory_items", [])
    if not tool_settings.get("memory", True):
        memory_items = []

    if action == "direct_retry":
        direct_messages = build_generator_messages(
            state["question"],
            state.get("workspace_type", "study"),
            memory_items,
            "",
            [],
            "direct",
            state.get("history", []),
        )
        revised = _chat_messages(direct_messages, temperature=0.3)
        updates = {
            "answer": revised,
            "route": "direct",
            "web_sources": [],
            "trace": _append_trace(
                {**state, "trace": trace},
                "Answered from model knowledge",
                "local files unrelated",
            ),
        }
        log_agent_node(
            "verify",
            {**state, **updates},
            verdict="direct_retry",
            answer_chars=len(revised),
        )
        return updates

    if action == "fallback_web":
        history = state.get("history", [])
        search_query = augment_question_with_history(state["question"], history)
        if len(search_query) > 500:
            search_query = search_query[:500]
        web_sources = search_web(search_query, max_results=5)
        trace = _append_trace(
            {**state, "trace": trace},
            "Searched the web after local miss",
            f"{len(web_sources)} result(s)",
        )
        route = "web_search"

    if action in ("fallback_web", "revise_web"):
        revise_messages = build_generator_messages(
            state["question"],
            state.get("workspace_type", "study"),
            memory_items,
            "",
            web_sources,
            "web_search",
            state.get("history", []),
        )
        revise_messages.append(
            {"role": "user", "content": GENERATOR_WEB_REVISE_USER_MESSAGE}
        )
        revised = _chat_messages(revise_messages, temperature=0.1)
        updates = {
            "answer": revised,
            "route": route if action == "revise_web" else "web_search",
            "web_sources": web_sources,
            "trace": _append_trace(
                {**state, "trace": trace},
                "Revised answer from web",
            ),
        }
        log_agent_node(
            "verify",
            {**state, **updates},
            verdict=action,
            answer_chars=len(revised),
            web_results=len(web_sources),
        )
        return updates

    revise_messages = build_generator_messages(
        state["question"],
        state.get("workspace_type", "study"),
        memory_items,
        state.get("context_block", ""),
        [],
        "file_rag",
        state.get("history", []),
    )
    revise_messages.append(
        {"role": "user", "content": GENERATOR_REVISE_USER_MESSAGE}
    )
    revised = _chat_messages(revise_messages, temperature=0.1)
    updates = {
        "answer": revised,
        "route": "file_rag",
        "web_sources": [],
        "trace": _append_trace(
            {**state, "trace": trace},
            "Revised answer from files",
        ),
    }
    log_agent_node(
        "verify",
        {**state, **updates},
        verdict="revise_local",
        answer_chars=len(revised),
    )
    return updates


def _route_after_memory(state: AgentState) -> str:
    route = state.get("route", "file_rag")
    if route == "direct":
        return "generate"
    if route == "web_search":
        return "web_search"
    return "retrieve"


def _route_after_retrieve(state: AgentState) -> str:
    route = state.get("route", "file_rag")
    if route != "hybrid":
        return "generate"

    indexed_files = state.get("indexed_files", [])
    if should_skip_web_after_retrieve(
        state["question"],
        route,
        len(state.get("retrieved_sources", [])),
        len(indexed_files),
    ):
        return "generate"
    return "web_search"


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("classify", classify_node)
    graph.add_node("load_memory", load_memory_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("code_search", code_search_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("generate", generate_node)
    graph.add_node("verify", verify_node)

    graph.add_edge(START, "classify")
    graph.add_edge("classify", "load_memory")
    graph.add_conditional_edges(
        "load_memory",
        _route_after_memory,
        {
            "generate": "generate",
            "retrieve": "retrieve",
            "web_search": "web_search",
        },
    )
    graph.add_edge("retrieve", "code_search")
    graph.add_conditional_edges(
        "code_search",
        _route_after_retrieve,
        {
            "web_search": "web_search",
            "generate": "generate",
        },
    )
    graph.add_edge("web_search", "generate")
    graph.add_edge("generate", "verify")
    graph.add_edge("verify", END)

    return graph.compile()


def get_agent_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
    return _agent_graph
