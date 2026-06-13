from __future__ import annotations


def derive_agent_label(
    *,
    files_read_count: int,
    web_tool_used: bool,
    web_sources_count: int,
    question: str,
) -> str:
    q = question.strip().lower()
    if (
        len(q) <= 30
        and q
        and any(g in q for g in ("hi", "hello", "hey", "thanks", "你好", "谢谢"))
    ):
        return "direct"

    has_web = web_tool_used or web_sources_count > 0
    has_local = files_read_count > 0

    if has_local and has_web:
        return "local+web"
    if has_local:
        return "local_files"
    if has_web:
        return "web_only"
    if not has_local and not has_web:
        return "insufficient"
    return "unknown"
