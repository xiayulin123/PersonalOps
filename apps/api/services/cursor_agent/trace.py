from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CursorRunCollector:
    answer_parts: list[str] = field(default_factory=list)
    files_read: set[str] = field(default_factory=set)
    web_tool_used: bool = False
    trace: list[dict] = field(default_factory=list)

    def consume_message(self, message: Any) -> None:
        msg_type = getattr(message, "type", None) or (
            message.get("type") if isinstance(message, dict) else None
        )
        if msg_type == "assistant":
            content = getattr(getattr(message, "message", None), "content", None)
            if content is None and isinstance(message, dict):
                inner = message.get("message") or {}
                content = inner.get("content") if isinstance(inner, dict) else None
            if content:
                for block in content:
                    text = getattr(block, "text", None)
                    if text is None and isinstance(block, dict):
                        text = block.get("text")
                    if text:
                        self.answer_parts.append(str(text))

        if msg_type == "tool_call":
            name = (getattr(message, "name", "") or "").lower()
            args = getattr(message, "args", None)
            if args is None and isinstance(message, dict):
                args = message.get("args")
            if any(token in name for token in ("web", "search", "tavily", "browse")):
                self.web_tool_used = True
            path = _extract_path_arg(args)
            if path:
                self.files_read.add(path)
            result = getattr(message, "result", None)
            if result is None and isinstance(message, dict):
                result = message.get("result")
            extra_path = _extract_path_from_result(result)
            if extra_path:
                self.files_read.add(extra_path)

    @property
    def answer(self) -> str:
        return "".join(self.answer_parts).strip()

    def sources_from_files(self) -> list[dict]:
        return [
            {
                "filename": name,
                "page": 1,
                "snippet": f"Read from workspace file: {name}",
            }
            for name in sorted(self.files_read)
        ]

    def append_trace(self, label: str, detail: str | None = None) -> None:
        self.trace.append(
            {"step": len(self.trace) + 1, "label": label, "detail": detail}
        )


def _extract_path_arg(args: Any) -> str | None:
    if args is None:
        return None
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return args if args.endswith((".pdf", ".md", ".txt", ".docx")) else None
    if isinstance(args, dict):
        for key in ("path", "file", "file_path", "target", "pattern"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _extract_path_from_result(result: Any) -> str | None:
    if isinstance(result, str):
        return result[:120] if len(result) < 120 else None
    return None
