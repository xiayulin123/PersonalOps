"""OCR extracted text sidecar tests (Plan B B3)."""

from __future__ import annotations

import os
from unittest.mock import patch

from services.storage.file_storage import (
    ensure_extracted_local_path,
    extracted_local_path,
    pages_to_extracted_text,
    save_extracted_text,
)


def test_pages_to_extracted_text():
    text = pages_to_extracted_text(
        [
            {"page": 1, "text": "Hello"},
            {"page": 2, "text": "World"},
        ]
    )
    assert "--- Page 1 ---" in text
    assert "Hello" in text
    assert "World" in text


def test_local_extracted_sidecar(tmp_path):
    original = tmp_path / "scan.pdf"
    original.write_bytes(b"%PDF-1.4")

    class FileRecord:
        id = "file-1"
        workspace_id = "ws-1"
        filename = "scan.pdf"
        path = str(original)
        storage_backend = "local"
        gcs_uri = None
        extracted_gcs_uri = None

    record = FileRecord()
    sidecar = save_extracted_text(
        file_record=record,
        user_id=None,
        text="OCR line one",
    )
    assert sidecar is None
    assert os.path.isfile(extracted_local_path(str(original)))
    assert ensure_extracted_local_path(record) == extracted_local_path(str(original))


@patch("services.storage.file_storage.gcs.upload_extracted_text")
def test_gcs_extracted_sidecar(mock_upload, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.storage.file_storage.settings.data_dir",
        str(tmp_path),
    )
    mock_upload.return_value = "gs://bucket/users/u1/ws/ws1/uploads/f1/scan.extracted.txt"

    class FileRecord:
        id = "f1"
        workspace_id = "ws1"
        filename = "scan.pdf"
        path = str(tmp_path / "cache" / "scan.pdf")
        storage_backend = "gcs"
        gcs_uri = "gs://bucket/users/u1/ws/ws1/uploads/f1/scan.pdf"
        extracted_gcs_uri = None

    record = FileRecord()
    uri = save_extracted_text(
        file_record=record,
        user_id="u1",
        text="Cloud OCR text",
    )
    assert uri == mock_upload.return_value
    record.extracted_gcs_uri = uri
    path = ensure_extracted_local_path(record)
    assert path is not None
    assert path.endswith("scan.extracted.txt")
