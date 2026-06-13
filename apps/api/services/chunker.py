import tiktoken

_ENCODING: tiktoken.Encoding | None = None


def _encoding() -> tiktoken.Encoding:
    global _ENCODING
    if _ENCODING is None:
        _ENCODING = tiktoken.get_encoding("cl100k_base")
    return _ENCODING


def chunk_text(
    pages: list[dict],
    max_tokens: int = 600,
    overlap: int = 100,
    *,
    workspace_id: str = "",
    file_id: str = "",
    filename: str = "",
) -> list[dict]:
    if overlap >= max_tokens:
        raise ValueError("overlap must be smaller than max_tokens")

    enc = _encoding()
    chunks: list[dict] = []
    chunk_index = 0

    for page in pages:
        text = page.get("text", "").strip()
        if not text:
            continue

        page_num = page.get("page", 1)
        tokens = enc.encode(text)
        start = 0

        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            piece = enc.decode(tokens[start:end]).strip()
            if piece:
                chunks.append(
                    {
                        "text": piece,
                        "workspace_id": workspace_id,
                        "file_id": file_id,
                        "filename": filename,
                        "page": page_num,
                        "chunk_index": chunk_index,
                    }
                )
                chunk_index += 1

            if end >= len(tokens):
                break
            start += max_tokens - overlap

    return chunks
