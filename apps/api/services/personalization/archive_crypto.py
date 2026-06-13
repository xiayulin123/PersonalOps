from __future__ import annotations

import gzip
import json
from base64 import urlsafe_b64encode
from hashlib import sha256
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


def _fernet_from_secret(secret: str) -> Fernet:
    raw = secret.strip()
    if not raw:
        raise ValueError("PERSONALIZATION_ARCHIVE_KEY is required for cloud archive")
    key = urlsafe_b64encode(sha256(raw.encode("utf-8")).digest())
    return Fernet(key)


def pack_records_jsonl(records: list[dict[str, Any]]) -> bytes:
    lines = [json.dumps(row, ensure_ascii=False) for row in records]
    payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    return gzip.compress(payload)


def unpack_records_jsonl(data: bytes) -> list[dict[str, Any]]:
    text = gzip.decompress(data).decode("utf-8")
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            rows.append(row)
    return rows


def encrypt_payload(secret: str, payload: bytes) -> bytes:
    return _fernet_from_secret(secret).encrypt(payload)


def decrypt_payload(secret: str, token: bytes) -> bytes:
    try:
        return _fernet_from_secret(secret).decrypt(token)
    except InvalidToken as exc:
        raise ValueError("Archive decryption failed — wrong PERSONALIZATION_ARCHIVE_KEY?") from exc
