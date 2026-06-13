from __future__ import annotations

import re

from services.agent.state import HistoryMessage, IndexedFile, MemoryItem, Route

ROUTER_SYSTEM_PROMPT = """You are the routing planner for PersonalOps, a local workspace AI assistant.

Your job is to classify the user's message into exactly ONE route:

- direct       : greetings, simple math, or meta questions about the app only
- file_rag     : answer primarily from uploaded/indexed workspace files (web search off)
- web_search   : answer primarily from the web when workspace files are not relevant
- hybrid       : check workspace files FIRST, then search the web, and synthesize one combined answer

Routing rules:
1. When file_search is enabled AND the workspace has indexed files, use file_rag ONLY for questions about those uploaded documents (assignments, novels, notes, resume, project files).
2. For general world knowledge (companies, people, science, history, "tell me about SpaceX"), use web_search when web_search is enabled; otherwise use direct.
3. Use hybrid ONLY when the question clearly needs current online info (news, latest versions, live data) AND local files may also help.
4. Use web_search when the question needs current online info and local files are unlikely to help.
5. Use direct for greetings, thanks, trivial math (e.g. "2+2"), meta questions about PersonalOps, OR general knowledge when web_search is disabled.
6. If the user says not to search the web / only use files (e.g. "不要上网", "根据文件"), choose file_rag.
7. Study workspace: bias strongly toward file_rag for course content, novels, characters.
8. Code workspace: bias toward file_rag for README, errors, project structure, synced GitHub files (_github_*), and indexed documents.
9. Life workspace: bias toward file_rag for personal notes, schedules, todos, and life documents.
10. Career workspace: bias toward file_rag for resume, cover letter, job description, and interview prep files.
11. Follow-up messages that omit the topic (e.g. "who is the author", "explain more") after a prior exchange MUST use file_rag when indexed files exist — resolve the referent from recent conversation history, NOT web_search.

Tool permission rules (must obey):
- If file_search is disabled, you MUST NOT choose file_rag or hybrid. Choose direct or web_search instead.
- If web_search is disabled, you MUST NOT choose web_search or hybrid. Choose direct or file_rag instead.
- If both file_search and web_search are disabled, choose direct.

Respond with ONLY one word from this exact list:
direct, file_rag, web_search, hybrid"""


GENERATOR_SYSTEM_PROMPT = """You are PersonalOps, a local workspace assistant.

Answer the user's question using the provided context when available.

Rules:
1. Answer the user's exact question in the first 1-2 sentences before any extra detail.
2. When workspace file context is provided, it is AUTHORITATIVE for questions about uploaded documents. Do NOT let web results override it.
3. If web results describe a different work that merely shares the same title as the user's file, IGNORE those web results completely.
4. If context is insufficient or unrelated to the question, say so briefly — then answer from web results (if provided) or from well-established general knowledge. Do NOT refuse to answer general knowledge questions.
5. Mention source filenames and page numbers when you rely on them.
6. Follow workspace memory preferences for language, tone, and explanation style.
7. For study workspaces: explain clearly, use examples when helpful, respect the user's preferred language.
8. For code workspaces: be practical and production-aware; reference files/functions when relevant.
9. For life workspaces: be organized and actionable; help with plans, reminders, and personal notes from files.
10. For career workspaces: be professional and concrete; tailor advice to resume, JD, and career documents.
9. Do not claim you searched files or the web unless context was actually provided below.
10. For scripts, novels, or character questions: ONLY use retrieved file snippets. Quote exact wording when possible.
11. For protagonist questions (主角/主人公): infer from narrative POV (e.g. second-person "你"), who drives scenes, and who is named most centrally. Name specific characters and cite pages.
12. Never invent dialogue, page numbers, or plot details that are not supported by the provided sources.
13. If different snippets conflict or are ambiguous, say so instead of guessing.
14. You may use simple Markdown: **bold** for headings, numbered lists for structure.
15. For hybrid route: answer from workspace files first. Add web context only if it clearly supplements the same topic — otherwise omit web entirely.
16. When prior user/assistant messages appear above, treat follow-ups as continuing that thread. Do not ask the user to repeat context you already have."""


VERIFIER_SYSTEM_PROMPT = """You are a lightweight answer verifier for PersonalOps.

Check whether the draft answer is appropriately grounded in the provided sources.

Rules:
1. If file or web context was provided, the answer should not make strong unsupported claims.
2. If no context was provided (direct route), general-knowledge answers are acceptable.
3. If file sources available is 0 and web sources available is 0, pass when the answer clearly states it cannot find enough evidence in workspace files (instead of guessing).
4. Return ONLY one word: pass or revise

Use revise when:
- The answer ignores workspace file context and relies on unrelated web knowledge.
- The answer gives a generic dictionary-style definition instead of answering about the topic from recent conversation (e.g. defining "author" when the user meant the author of a project just discussed).
- The answer does not directly address the user's question (e.g. summarizes scenes but never names the protagonist).
- The answer hallucinates facts not in the provided sources."""


_HISTORY_MAX_CHARS_USER = 600
_HISTORY_MAX_CHARS_ASSISTANT = 1500
_AUGMENT_PRIOR_USER_CHARS = 400
_AUGMENT_PRIOR_ASSISTANT_CHARS = 800


def _trim_history_content(role: str, content: str) -> str:
    """Asymmetric caps: keep more assistant text (facts + citations live there)."""
    limit = (
        _HISTORY_MAX_CHARS_ASSISTANT
        if role == "assistant"
        else _HISTORY_MAX_CHARS_USER
    )
    if len(content) <= limit:
        return content
    if role == "assistant":
        head = int(limit * 0.6)
        tail = limit - head - 5
        return content[:head] + "\n...\n" + content[-tail:]
    return content[:limit] + "..."


def build_history_block(history: list[HistoryMessage]) -> str:
    if not history:
        return ""

    lines = ["Recent conversation (oldest first):"]
    for message in history:
        role = message.get("role", "user")
        content = (message.get("content") or "").strip()
        if not content:
            continue
        content = _trim_history_content(role, content)
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


_FOLLOW_UP_PATTERNS = (
    r"第[一二三四五六七八九十\d]+",
    r"上面",
    r"刚才",
    r"之前",
    r"这个",
    r"那个",
    r"继续",
    r"再解释",
    r"more detail",
    r"explain.*more",
    r"point\s*\d",
    r"不要上网",
    r"根据文件",
    r"from (the )?files?",
    r"\bwho\s+is\b",
    r"\bwho'?s\b",
    r"\bauthor\b",
    r"\bcreator\b",
    r"\bowner\b",
    r"\bmaintainer\b",
    r"i mean\b",
    r"你?说的",
    r"刚才说的",
)

_FOLLOW_UP_MAX_WORDS = 8
_FOLLOW_UP_MAX_CHARS = 120
_FOLLOW_UP_FRAGMENT_MAX_WORDS = 4

_CONTINUATION_WORDS = (
    r"^(and|also|ok|okay|yes|no|why|how|when|where)\b",
    r"^(那|然后|所以|为什么|怎么|继续)",
)


def _is_trivial_message(question: str) -> bool:
    """Greetings and tiny math are never treated as context-dependent follow-ups."""
    q = question.strip().lower()
    if not q:
        return True
    if re.fullmatch(r"[\d\s\+\-\*/\.\=]+", q):
        return True
    if len(q) <= 30 and re.search(
        r"\b(hi|hello|hey|thanks|thank you|你好|谢谢|嗨)\b", q
    ):
        return True
    return False


def _is_short_message(question: str) -> bool:
    word_count = len(question.split())
    return (
        len(question) <= _FOLLOW_UP_MAX_CHARS
        and word_count <= _FOLLOW_UP_MAX_WORDS
    )


def _last_exchange(history: list[HistoryMessage]) -> tuple[str, str]:
    last_user = ""
    last_assistant = ""
    for message in reversed(history):
        role = message.get("role")
        content = (message.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant" and not last_assistant:
            last_assistant = content
        elif role == "user" and not last_user:
            last_user = content
        if last_user and last_assistant:
            break
    return last_user, last_assistant


def is_vague_follow_up(
    question: str,
    history: list[HistoryMessage] | None,
) -> bool:
    """Detect ellipsis questions that refer to the prior turn.

    Requires a signal (pattern, continuation word, or very short fragment).
    Short but self-contained new questions are NOT follow-ups.
    """
    if not history:
        return False

    trimmed = question.strip()
    if not trimmed or _is_trivial_message(trimmed):
        return False
    if needs_web_search(trimmed):
        return False
    if wants_file_only(trimmed):
        return True

    last_user, last_assistant = _last_exchange(history)
    if not last_user and not last_assistant:
        return False

    if any(re.search(pattern, trimmed, re.IGNORECASE) for pattern in _FOLLOW_UP_PATTERNS):
        return True

    if not _is_short_message(trimmed):
        return False

    word_count = len(trimmed.split())

    # Short but reads like a standalone new question (e.g. "What is EDF scheduling?")
    if "?" in trimmed and word_count >= 4:
        if not any(re.search(p, trimmed, re.IGNORECASE) for p in _FOLLOW_UP_PATTERNS):
            return False

    if any(re.search(p, trimmed, re.IGNORECASE) for p in _CONTINUATION_WORDS):
        return True

    # Very short fragment (e.g. "author?", "point 2") likely refers to prior turn
    return word_count <= _FOLLOW_UP_FRAGMENT_MAX_WORDS


def augment_question_with_history(
    question: str, history: list[HistoryMessage]
) -> str:
    """Broaden retrieval/routing for vague follow-up questions."""
    trimmed = question.strip()
    if not trimmed or not history:
        return trimmed

    if not is_vague_follow_up(trimmed, history):
        return trimmed

    last_user, last_assistant = _last_exchange(history)
    parts = [trimmed, "", "Conversation context (resolve referents from this):"]
    if last_user:
        parts.append(
            "Prior user question: "
            + _trim_history_content("user", last_user)[:_AUGMENT_PRIOR_USER_CHARS]
        )
    if last_assistant:
        snippet = _trim_history_content("assistant", last_assistant)[
            :_AUGMENT_PRIOR_ASSISTANT_CHARS
        ]
        parts.append(f"Prior assistant answer: {snippet}")
    return "\n".join(parts)


def build_router_user_prompt(
    question: str,
    workspace_type: str,
    tool_settings: dict,
    indexed_files: list[IndexedFile] | None = None,
    history: list[HistoryMessage] | None = None,
) -> str:
    file_search = tool_settings.get("file_search", True)
    web_search = tool_settings.get("web_search", False)
    memory = tool_settings.get("memory", True)
    github_read = tool_settings.get("github_read", False)
    code_search = tool_settings.get("code_search", False)

    file_lines = ["Indexed workspace files (searchable):"]
    files = indexed_files or []
    if files:
        for item in files:
            file_lines.append(f"- {item['filename']} ({item['chunk_count']} chunks)")
    else:
        file_lines.append("- none")

    return f"""Workspace type: {workspace_type}

Tool settings:
- file_search: {file_search}
- web_search: {web_search}
- memory: {memory}
- github_read: {github_read}
- code_search: {code_search}

{chr(10).join(file_lines)}

{build_history_block(history or [])}

User message:
{question.strip()}"""


def build_memory_block(memory_items: list[MemoryItem]) -> str:
    if not memory_items:
        return ""

    facts = [i for i in memory_items if i.get("kind", "memory") == "memory"]
    rules = [i for i in memory_items if i.get("kind") == "rule"]
    habits = [i for i in memory_items if i.get("kind") == "habit"]

    sections: list[str] = []

    if facts:
        lines = ["User facts:"]
        lines.extend(f"- {item['key']}: {item['value']}" for item in facts)
        sections.append("\n".join(lines))

    if rules:
        lines = ["Rules (follow these constraints):"]
        lines.extend(f"- {item['key']}: {item['value']}" for item in rules)
        sections.append("\n".join(lines))

    if habits:
        lines = ["Habits (style and recurring interests):"]
        lines.extend(f"- {item['key']}: {item['value']}" for item in habits)
        sections.append("\n".join(lines))

    if not sections:
        lines = ["Workspace memory preferences:"]
        lines.extend(f"- {item['key']}: {item['value']}" for item in memory_items)
        return "\n".join(lines)

    return "Workspace personalization:\n" + "\n\n".join(sections)


def build_file_context_block(context_block: str) -> str:
    if not context_block.strip():
        return "No workspace file context was retrieved."
    return f"Workspace file context:\n{context_block.strip()}"


def build_web_context_block(web_sources: list[dict]) -> str:
    if not web_sources:
        return "No web search context was retrieved."

    blocks: list[str] = ["Web search context:"]
    for index, source in enumerate(web_sources, start=1):
        title = source.get("title", "Untitled")
        url = source.get("url", "")
        snippet = source.get("snippet", "")
        blocks.append(f"[Web {index}: {title}]\nURL: {url}\n{snippet.strip()}")
    return "\n\n".join(blocks)


def build_generator_context_user_content(
    question: str,
    workspace_type: str,
    memory_items: list[MemoryItem],
    context_block: str,
    web_sources: list[dict],
    route: Route,
) -> str:
    """Final user turn: workspace context + current question (history is separate messages)."""
    sections = [
        f"Workspace type: {workspace_type}",
        f"Route: {route}",
        build_memory_block(memory_items),
        build_file_context_block(context_block),
        build_web_context_block(web_sources),
        f"User question:\n{question.strip()}",
        "Write the final answer now.",
    ]
    return "\n\n".join(section for section in sections if section.strip())


def build_generator_messages(
    question: str,
    workspace_type: str,
    memory_items: list[MemoryItem],
    context_block: str,
    web_sources: list[dict],
    route: Route,
    history: list[HistoryMessage] | None = None,
) -> list[dict[str, str]]:
    """OpenAI chat messages: system, prior turns, then context + current question."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": GENERATOR_SYSTEM_PROMPT},
    ]
    for message in history or []:
        role = message.get("role")
        content = (message.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        messages.append(
            {
                "role": role,
                "content": _trim_history_content(role, content),
            }
        )
    messages.append(
        {
            "role": "user",
            "content": build_generator_context_user_content(
                question,
                workspace_type,
                memory_items,
                context_block,
                web_sources,
                route,
            ),
        }
    )
    return messages


GENERATOR_REVISE_USER_MESSAGE = (
    "Your previous draft failed verification. Rewrite using ONLY workspace "
    "file context. Directly answer the user's question."
)

GENERATOR_WEB_REVISE_USER_MESSAGE = (
    "Your previous draft failed verification. Workspace files did not contain "
    "enough evidence. Rewrite using ONLY the web search results below. "
    "Directly answer the user's question."
)

INSUFFICIENT_LOCAL_EVIDENCE_ANSWER = (
    "I could not find enough evidence in your workspace files to answer this "
    "question, and web search is disabled for this workspace. Try uploading "
    "relevant documents or enabling web search in Tools."
)


def build_generator_user_prompt(
    question: str,
    workspace_type: str,
    memory_items: list[MemoryItem],
    context_block: str,
    web_sources: list[dict],
    route: Route,
    history: list[HistoryMessage] | None = None,
) -> str:
    """Flat single-user prompt (legacy). Prefer build_generator_messages for generation."""
    sections = [
        f"Workspace type: {workspace_type}",
        f"Route: {route}",
        build_memory_block(memory_items),
        build_history_block(history or []),
        build_file_context_block(context_block),
        build_web_context_block(web_sources),
        f"User question:\n{question.strip()}",
        "Write the final answer now.",
    ]
    return "\n\n".join(section for section in sections if section.strip())


def build_verifier_user_prompt(
    question: str,
    answer: str,
    route: Route,
    retrieved_sources: list[dict],
    web_sources: list[dict],
) -> str:
    file_count = len(retrieved_sources)
    web_count = len(web_sources)

    return f"""Route: {route}
File sources available: {file_count}
Web sources available: {web_count}

User question:
{question.strip()}

Draft answer:
{answer.strip()}"""


_FILE_ONLY_PATTERNS = (
    r"不要上网",
    r"别上网",
    r"不要搜索",
    r"不要查网",
    r"根据文件",
    r"只看文件",
    r"从文件",
    r"based on (the )?files?",
    r"from (the )?files?",
    r"don'?t search",
    r"no web",
    r"without web",
)

_WEB_NEEDED_PATTERNS = (
    r"最新",
    r"今年",
    r"20[2-9][0-9]",
    r"新闻",
    r"股价",
    r"天气",
    r"currently",
    r"latest",
    r"news",
    r"today",
    r"right now",
    r"maintained",
    r"still (active|popular|used)",
)


def wants_file_only(question: str) -> bool:
    q = question.strip()
    if not q:
        return False
    return any(re.search(pattern, q, re.IGNORECASE) for pattern in _FILE_ONLY_PATTERNS)


def needs_web_search(question: str) -> bool:
    q = question.strip()
    if not q:
        return False
    if wants_file_only(q):
        return False
    if is_general_knowledge_question(q):
        return True
    return any(re.search(pattern, q, re.IGNORECASE) for pattern in _WEB_NEEDED_PATTERNS)


_GENERAL_KNOWLEDGE_PATTERNS = (
    r"^tell me about\b",
    r"^what is\b",
    r"^what are\b",
    r"^who is\b",
    r"^who are\b",
    r"^explain\b",
    r"^describe\b",
    r"介绍一下",
    r"什么是",
    r"告诉我.*是什么",
    r"讲讲",
    r"说说",
)


def is_general_knowledge_question(question: str) -> bool:
    """Broad factual questions not explicitly about the user's uploaded files."""
    q = question.strip()
    if not q or wants_file_only(q):
        return False
    return any(re.search(pattern, q, re.IGNORECASE) for pattern in _GENERAL_KNOWLEDGE_PATTERNS)


def answer_indicates_local_miss(answer: str) -> bool:
    """Draft says workspace files did not contain the answer."""
    text = answer.strip().lower()
    if not text:
        return True
    markers = (
        "cannot find enough evidence",
        "could not find enough evidence",
        "无法在",
        "找不到",
        "没有足够",
        "没有关于",
        "文件中没有",
        "提供的文件",
        "workspace files",
        "workspace documents",
        "not find specific information",
        "not in the provided",
    )
    return any(marker in text for marker in markers)


def should_skip_web_after_retrieve(
    question: str,
    route: Route,
    retrieved_count: int,
    indexed_files_count: int,
) -> bool:
    """Skip web in hybrid flow when local retrieval is sufficient."""
    if route != "hybrid":
        return True
    if wants_file_only(question):
        return True
    # Local miss: no chunks — allow hybrid to continue to web search.
    if retrieved_count == 0:
        return False
    # Have chunks and the question does not need live/web info.
    if not needs_web_search(question):
        return True
    return False


def resolve_verify_failure_action(
    *,
    retrieved_sources: list,
    web_sources: list,
    tool_settings: dict,
    answer: str = "",
) -> str:
    """Choose post-verify recovery: revise_local | fallback_web | revise_web | insufficient | direct_retry."""
    has_local = len(retrieved_sources) > 0
    has_web = len(web_sources) > 0
    web_enabled = bool(tool_settings.get("web_search", False))

    if has_local and answer_indicates_local_miss(answer):
        if web_enabled:
            return "revise_web" if has_web else "fallback_web"
        return "direct_retry"

    if has_local:
        return "revise_local"

    if web_enabled:
        return "revise_web" if has_web else "fallback_web"

    return "insufficient"


def _is_trivial_direct_question(question: str) -> bool:
    q = question.strip().lower()
    if not q:
        return True
    if re.fullmatch(r"[\d\s\+\-\*/\.\=]+", q):
        return True
    if len(q) <= 30 and re.search(r"\b(hi|hello|hey|thanks|thank you|你好|谢谢|嗨)\b", q):
        return True
    return False


def normalize_route(
    raw: str,
    tool_settings: dict,
    question: str = "",
    indexed_files_count: int = 0,
    history: list[HistoryMessage] | None = None,
) -> Route:
    """Map model output to a valid route and enforce tool permissions."""
    cleaned = raw.strip().lower()
    allowed: set[Route] = {"direct", "file_rag", "web_search", "hybrid"}

    route: Route = cleaned if cleaned in allowed else "file_rag"

    file_search = tool_settings.get("file_search", True)
    web_search = tool_settings.get("web_search", False)

    if not file_search and route in ("file_rag", "hybrid"):
        route = "web_search" if web_search else "direct"

    if not web_search and route in ("web_search", "hybrid"):
        route = "file_rag" if file_search else "direct"

    if not file_search and not web_search:
        route = "direct"

    if _is_trivial_direct_question(question):
        return "direct"

    if wants_file_only(question) and file_search:
        return "file_rag"

    if web_search and is_general_knowledge_question(question):
        return "web_search"

    if file_search and web_search and route == "hybrid" and not needs_web_search(question):
        route = "file_rag"

    if file_search and web_search and route == "direct":
        route = "web_search" if is_general_knowledge_question(question) else (
            "file_rag" if indexed_files_count > 0 else "web_search"
        )

    if file_search and not web_search and route == "direct":
        route = "file_rag" if indexed_files_count > 0 and not is_general_knowledge_question(question) else "direct"

    if (
        file_search
        and indexed_files_count > 0
        and is_vague_follow_up(question, history)
        and route in ("web_search", "direct")
    ):
        route = "file_rag"

    return route
