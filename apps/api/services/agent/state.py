from __future__ import annotations

from typing import Literal, TypedDict

Route = Literal["direct", "file_rag", "web_search", "hybrid"]


class TraceStep(TypedDict, total=False):
    step: int
    label: str
    detail: str | None


class MemoryItem(TypedDict, total=False):
    key: str
    value: str
    kind: str
    source: str


class IndexedFile(TypedDict):
    filename: str
    chunk_count: int


class HistoryMessage(TypedDict):
    role: str  # "user" | "assistant"
    content: str


class AgentState(TypedDict, total=False):
    workspace_id: str
    workspace_type: str  # "study" | "code" | "life" | "career"
    question: str
    history: list[HistoryMessage]
    tool_settings: dict
    memory_items: list[MemoryItem]
    indexed_files: list[IndexedFile]
    route: Route
    trace: list[TraceStep]
    retrieved_sources: list[dict]
    retrieved_documents: list[str]
    retrieved_metadatas: list[dict]
    web_sources: list[dict]
    context_block: str
    answer: str
