"""Study-specific RAG retrieval filtered by selected course files."""

from __future__ import annotations

from services.indexer import _collection, _embed_texts
from services.rag import _build_context_block_with_lines, _build_sources, _chunk_key

DEFAULT_STUDY_QUERY = (
    "key concepts definitions theorems algorithms exam topics formulas examples"
)


def retrieve_study_context(
    *,
    workspace_id: str,
    file_ids: list[str],
    topic_hint: str | None = None,
    max_chunks: int = 24,
) -> tuple[str, list[dict], list[str], list[dict]]:
    """
    Return (context_block, sources, documents, metadatas) for LLM generation.

    sources items include file_id when available in Chroma metadata.
    """
    if not file_ids:
        return "", [], [], []

    max_chunks = max(1, min(max_chunks, 32))
    collection = _collection(workspace_id)
    if collection.count() == 0:
        return "", [], [], []

    query_text = (topic_hint or "").strip() or DEFAULT_STUDY_QUERY
    query_embedding = _embed_texts([query_text])[0]

    file_id_set = set(file_ids)
    where_filter: dict | None
    if len(file_ids) == 1:
        where_filter = {"file_id": file_ids[0]}
    else:
        where_filter = {"file_id": {"$in": file_ids}}

    n_results = min(max_chunks * 2, 48)
    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas"],
        )
    except Exception:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas"],
        )

    documents: list[str] = []
    metadatas: list[dict] = []
    seen: set[str] = set()

    for document, metadata in zip(
        results.get("documents", [[]])[0],
        results.get("metadatas", [[]])[0],
    ):
        if len(documents) >= max_chunks:
            break
        meta = metadata or {}
        file_id = str(meta.get("file_id", ""))
        if file_id not in file_id_set:
            continue
        key = _chunk_key(meta)
        if key in seen:
            continue
        seen.add(key)
        documents.append(document)
        metadatas.append(meta)

    if not documents:
        return "", [], [], []

    sources = _build_sources(documents, metadatas)
    for source, metadata in zip(sources, metadatas):
        file_id = metadata.get("file_id")
        if file_id:
            source["file_id"] = str(file_id)

    context_block = _build_context_block_with_lines(documents, metadatas)
    return context_block, sources, documents, metadatas
