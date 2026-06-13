from __future__ import annotations

import re

from services.indexer import _collection, _embed_texts, _openai_client

SYSTEM_PROMPT = """You are PersonalOps, a local workspace assistant.
Answer the user's question using ONLY the provided context from their uploaded files.
If the context does not contain enough information, say you cannot find it in the workspace documents.
Be concise and factual. Do not invent details."""

_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+")


def _chunk_key(metadata: dict) -> str:
    return f"{metadata.get('file_id', '')}_{metadata.get('chunk_index', '')}"


def expand_retrieval_query(question: str) -> str:
    """Broaden retrieval for character/protagonist questions."""
    trimmed = question.strip()
    if not trimmed:
        return trimmed

    title_match = re.search(r"《([^》]+)》", trimmed)
    title = title_match.group(1) if title_match else ""

    if re.search(r"主角|主人公|叙述者|视角", trimmed):
        parts = [trimmed]
        if title:
            parts.append(title)
        parts.append("主角 主人公 大当家 叙述视角 你")
        return " ".join(parts)

    if title and title not in trimmed.replace(f"《{title}》", ""):
        return f"{trimmed} {title}"

    return trimmed


def _extract_cjk_keywords(question: str) -> list[str]:
    """Extract Chinese keyword segments for metadata/document filtering."""
    parts = _CJK_PATTERN.findall(question)
    seen: set[str] = set()
    keywords: list[str] = []
    for part in parts:
        if len(part) >= 2 and part not in seen:
            seen.add(part)
            keywords.append(part)
    return keywords


def _build_context_block(documents: list[str], metadatas: list[dict]) -> str:
    return _build_context_block_with_lines(documents, metadatas)


def _build_sources(documents: list[str], metadatas: list[dict]) -> list[dict]:
    sources: list[dict] = []
    for document, metadata in zip(documents, metadatas):
        source = {
            "filename": metadata.get("filename", "unknown"),
            "page": int(metadata.get("page", 1)),
            "snippet": document.strip()[:240],
        }
        line = metadata.get("line")
        if line is not None:
            source["line"] = int(line)
        if metadata.get("source_type"):
            source["source_type"] = metadata["source_type"]
        sources.append(source)
    return sources


def _build_context_block_with_lines(documents: list[str], metadatas: list[dict]) -> str:
    blocks: list[str] = []
    for index, (document, metadata) in enumerate(zip(documents, metadatas), start=1):
        filename = metadata.get("filename", "unknown")
        if metadata.get("line") is not None:
            location = f"line {metadata['line']}"
        else:
            location = f"page {metadata.get('page', 1)}"
        blocks.append(
            f"[Source {index}: {filename}, {location}]\n{document.strip()}"
        )
    return "\n\n".join(blocks)


def merge_code_search_hits(
    documents: list[str],
    metadatas: list[dict],
    sources: list[dict],
    code_hits: list[dict],
    *,
    max_total: int = 15,
) -> tuple[list[str], list[dict], list[dict], str]:
    """Prepend exact ripgrep matches ahead of vector retrieval results."""
    if not code_hits:
        context = _build_context_block_with_lines(documents, metadatas) if documents else ""
        return documents, metadatas, sources, context

    seen = {_chunk_key(metadata) for metadata in metadatas}
    merged_docs = list(documents)
    merged_metas = list(metadatas)
    merged_sources = list(sources)

    for hit in code_hits:
        if len(merged_docs) >= max_total:
            break

        filename = hit.get("filename", "unknown")
        line_number = int(hit.get("line_number", 1))
        snippet = (hit.get("snippet") or "").strip()
        dedupe_key = f"code::{filename}::{line_number}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        document = snippet or f"(match in {filename})"
        metadata = {
            "filename": filename,
            "page": 1,
            "line": line_number,
            "source_type": "code_search",
            "chunk_index": dedupe_key,
            "file_id": dedupe_key,
        }

        merged_docs.insert(0, document)
        merged_metas.insert(0, metadata)
        source = {
            "filename": filename,
            "page": 1,
            "line": line_number,
            "snippet": document[:240],
            "source_type": "code_search",
        }
        merged_sources.insert(0, source)

    context = (
        _build_context_block_with_lines(merged_docs, merged_metas) if merged_docs else ""
    )
    return merged_docs, merged_metas, merged_sources, context


def _merge_keyword_hits(
    collection,
    question: str,
    documents: list[str],
    metadatas: list[dict],
    n_results: int,
) -> tuple[list[str], list[dict]]:
    keywords = _extract_cjk_keywords(question)
    if not keywords:
        return documents, metadatas

    seen = {_chunk_key(metadata) for metadata in metadatas}
    merged_docs = list(documents)
    merged_metas = list(metadatas)

    for keyword in keywords[:5]:
        if len(merged_docs) >= n_results:
            break
        try:
            keyword_results = collection.get(
                where_document={"$contains": keyword},
                include=["documents", "metadatas"],
                limit=8,
            )
        except Exception:
            continue

        for document, metadata in zip(
            keyword_results.get("documents", []),
            keyword_results.get("metadatas", []),
        ):
            if len(merged_docs) >= n_results:
                break
            key = _chunk_key(metadata)
            if key in seen:
                continue
            seen.add(key)
            merged_docs.append(document)
            merged_metas.append(metadata)

    return merged_docs, merged_metas


async def retrieve_chunks(
    workspace_id: str, question: str, n_results: int = 10
) -> dict:
    """
    Retrieve relevant file chunks for a workspace question.

    Returns:
    {
      "documents": [...],
      "metadatas": [...],
      "sources": [{"filename", "page", "snippet"}, ...]
    }
    """
    empty = {"documents": [], "metadatas": [], "sources": []}

    trimmed = question.strip()
    if not trimmed:
        return empty

    n_results = max(1, min(n_results, 20))
    collection = _collection(workspace_id)
    if collection.count() == 0:
        return empty

    query_embedding = _embed_texts([trimmed])[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas"],
    )

    documents = list(results.get("documents", [[]])[0])
    metadatas = list(results.get("metadatas", [[]])[0])

    documents, metadatas = _merge_keyword_hits(
        collection, trimmed, documents, metadatas, n_results
    )

    if not documents:
        return empty

    return {
        "documents": documents,
        "metadatas": metadatas,
        "sources": _build_sources(documents, metadatas),
    }


async def answer_question(workspace_id: str, question: str) -> dict:
    """Phase 1 chat path — kept for backward compatibility until Step 2.8."""
    retrieved = await retrieve_chunks(workspace_id, question, n_results=10)
    documents = retrieved["documents"]
    metadatas = retrieved["metadatas"]
    sources = retrieved["sources"]

    if not documents:
        collection = _collection(workspace_id)
        if collection.count() == 0:
            return {
                "answer": "No indexed documents found in this workspace. Upload a file and wait until status is ready.",
                "sources": [],
            }
        return {
            "answer": "I could not find relevant passages in your workspace documents.",
            "sources": [],
        }

    context = _build_context_block(documents, metadatas)
    user_prompt = f"""Context from workspace documents:

{context}

Question: {question}

Answer using the context above. Mention which source files you used when relevant."""

    response = _openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    answer = response.choices[0].message.content or ""
    return {
        "answer": answer.strip(),
        "sources": sources,
    }
