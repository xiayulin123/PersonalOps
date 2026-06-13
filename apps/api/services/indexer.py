from __future__ import annotations

import chromadb
from chromadb.api.models.Collection import Collection

from config import settings
from services.openai_runtime import get_openai_client

_client: chromadb.PersistentClient | None = None


def _chroma_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    return _client


def _openai_client():
    return get_openai_client()


def _collection(workspace_id: str) -> Collection:
    return _chroma_client().get_or_create_collection(name=f"ws_{workspace_id}")


def _embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = _openai_client().embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in response.data]


def index_file(workspace_id: str, file_id: str, chunks: list[dict]) -> int:
    """Embed chunks with OpenAI and store them in Chroma."""
    if not chunks:
        return 0

    collection = _collection(workspace_id)
    delete_file_chunks(workspace_id, file_id)

    batch_size = 100
    indexed = 0

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [chunk["text"] for chunk in batch]
        embeddings = _embed_texts(texts)

        ids = [f"{file_id}_{chunk['chunk_index']}" for chunk in batch]
        metadatas = [
            {
                "workspace_id": chunk.get("workspace_id", workspace_id),
                "file_id": file_id,
                "filename": chunk.get("filename", ""),
                "page": int(chunk.get("page", 1)),
                "chunk_index": int(chunk.get("chunk_index", 0)),
            }
            for chunk in batch
        ]

        collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        indexed += len(batch)

    return indexed


def delete_file_chunks(workspace_id: str, file_id: str) -> None:
    """Remove all vectors for one file from the workspace collection."""
    client = _chroma_client()
    try:
        collection = client.get_collection(name=f"ws_{workspace_id}")
    except Exception:
        return
    collection.delete(where={"file_id": file_id})
