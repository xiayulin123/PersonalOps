"""Unit tests for personalization P3 — archive crypto and in-memory provider."""

from datetime import date

from services.personalization.archive import object_key_for_period
from services.personalization.archive_crypto import (
    decrypt_payload,
    encrypt_payload,
    pack_records_jsonl,
    unpack_records_jsonl,
)


def test_encrypt_decrypt_roundtrip():
    secret = "test-archive-key-123"
    records = [{"id": "1", "content_redacted": "hello OAuth"}]
    packed = pack_records_jsonl(records)
    token = encrypt_payload(secret, packed)
    restored = unpack_records_jsonl(decrypt_payload(secret, token))
    assert restored == records


def test_object_key_path():
    key = object_key_for_period("ws-abc", date(2026, 6, 11))
    assert key == "ws-abc/2026/06/11.jsonl.gz.enc"


class _MemoryArchive:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self.secret = "mem-key"

    def object_key(self, workspace_id: str, period_start: date) -> str:
        return object_key_for_period(workspace_id, period_start)

    def upload_period(self, workspace_id, period_start, records):
        from services.personalization.archive_crypto import encrypt_payload, pack_records_jsonl

        key = self.object_key(workspace_id, period_start)
        self._store[key] = encrypt_payload(self.secret, pack_records_jsonl(records))
        return f"memory://{key}"

    def object_exists(self, workspace_id, period_start):
        return self.object_key(workspace_id, period_start) in self._store

    def download_period(self, workspace_id, period_start):
        from services.personalization.archive_crypto import (
            decrypt_payload,
            unpack_records_jsonl,
        )

        key = self.object_key(workspace_id, period_start)
        blob = self._store.get(key)
        if blob is None:
            return []
        return unpack_records_jsonl(decrypt_payload(self.secret, blob))


def test_memory_archive_upload_download():
    archive = _MemoryArchive()
    ws = "workspace-1"
    day = date(2026, 6, 5)
    records = [{"content_redacted": "Explain EDF scheduling"}]
    uri = archive.upload_period(ws, day, records)
    assert uri.startswith("memory://")
    assert archive.object_exists(ws, day)
    assert archive.download_period(ws, day) == records
