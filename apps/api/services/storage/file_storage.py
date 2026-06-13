"""File storage abstraction: local disk vs GCS (Plan B B3)."""

from __future__ import annotations

import os
import uuid

from config import settings
from models import File
from services.storage import gcs_app_storage as gcs


def gcs_cache_dir(workspace_id: str, file_id: str) -> str:
    return os.path.join(settings.data_dir, "_gcs_cache", workspace_id, file_id)


def extracted_local_path(original_path: str) -> str:
    base, _ext = os.path.splitext(original_path)
    return f"{base}.extracted.txt"


def pages_to_extracted_text(pages: list[dict]) -> str:
    parts: list[str] = []
    for page in pages:
        text = (page.get("text") or "").strip()
        if not text:
            continue
        page_no = page.get("page", 1)
        parts.append(f"--- Page {page_no} ---\n{text}")
    return "\n\n".join(parts)


def should_store_uploads_in_gcs(*, user_id: str | None) -> bool:
    return gcs.is_gcs_app_storage_enabled() and bool(user_id)


def save_uploaded_file(
    *,
    workspace_id: str,
    user_id: str | None,
    filename: str,
    content: bytes,
) -> tuple[str, str, str, str | None, int]:
    """Returns file_id, storage_backend, local_path, gcs_uri, size_bytes."""
    file_id = str(uuid.uuid4())
    size_bytes = len(content)

    if should_store_uploads_in_gcs(user_id=user_id):
        assert user_id is not None
        gcs_uri = gcs.upload_user_file(
            user_id=user_id,
            workspace_id=workspace_id,
            file_id=file_id,
            filename=filename,
            content=content,
        )
        cache_dir = gcs_cache_dir(workspace_id, file_id)
        os.makedirs(cache_dir, exist_ok=True)
        local_path = os.path.join(cache_dir, filename)
        with open(local_path, "wb") as handle:
            handle.write(content)
        return file_id, "gcs", local_path, gcs_uri, size_bytes

    workspace_dir = os.path.join(settings.uploads_dir, workspace_id)
    os.makedirs(workspace_dir, exist_ok=True)
    local_path = os.path.join(workspace_dir, filename)
    with open(local_path, "wb") as handle:
        handle.write(content)
    return file_id, "local", local_path, None, size_bytes


def save_extracted_text(
    *,
    file_record: File,
    user_id: str | None,
    text: str,
) -> str | None:
    """Persist OCR/plain-text sidecar. Returns extracted_gcs_uri when stored in GCS."""
    content = text.encode("utf-8")
    filename = os.path.basename(file_record.filename)
    base, _ext = os.path.splitext(filename)
    extracted_name = f"{base}.extracted.txt"

    if file_record.storage_backend == "gcs" and file_record.gcs_uri and user_id:
        extracted_uri = gcs.upload_extracted_text(
            user_id=user_id,
            workspace_id=file_record.workspace_id,
            file_id=file_record.id,
            original_filename=filename,
            content=content,
        )
        cache_dir = gcs_cache_dir(file_record.workspace_id, file_record.id)
        os.makedirs(cache_dir, exist_ok=True)
        local_extracted = os.path.join(cache_dir, extracted_name)
        with open(local_extracted, "wb") as handle:
            handle.write(content)
        return extracted_uri

    local_extracted = extracted_local_path(file_record.path)
    os.makedirs(os.path.dirname(local_extracted), exist_ok=True)
    with open(local_extracted, "wb") as handle:
        handle.write(content)
    return None


def ensure_local_path(file_record: File) -> str:
    if file_record.storage_backend != "gcs" or not file_record.gcs_uri:
        return file_record.path

    if os.path.isfile(file_record.path):
        return file_record.path

    cache_dir = gcs_cache_dir(file_record.workspace_id, file_record.id)
    os.makedirs(cache_dir, exist_ok=True)
    local_path = os.path.join(cache_dir, file_record.filename)
    gcs.download_user_file(file_record.gcs_uri, local_path)
    return local_path


def ensure_extracted_local_path(file_record: File) -> str | None:
    """Return local path to OCR sidecar text when available."""
    filename = os.path.basename(file_record.filename)
    base, _ext = os.path.splitext(filename)
    extracted_name = f"{base}.extracted.txt"

    if file_record.extracted_gcs_uri:
        cache_dir = gcs_cache_dir(file_record.workspace_id, file_record.id)
        os.makedirs(cache_dir, exist_ok=True)
        local_path = os.path.join(cache_dir, extracted_name)
        if not os.path.isfile(local_path):
            gcs.download_user_file(file_record.extracted_gcs_uri, local_path)
        return local_path

    if file_record.storage_backend == "local":
        sidecar = extracted_local_path(file_record.path)
        if os.path.isfile(sidecar):
            return sidecar

    if file_record.storage_backend == "gcs":
        cache_dir = gcs_cache_dir(file_record.workspace_id, file_record.id)
        local_path = os.path.join(cache_dir, extracted_name)
        if os.path.isfile(local_path):
            return local_path

    return None


def cleanup_temp_cache(file_record: File) -> None:
    if file_record.storage_backend != "gcs":
        return
    cache_root = os.path.join(
        settings.data_dir, "_gcs_cache", file_record.workspace_id, file_record.id
    )
    if not os.path.isdir(cache_root):
        return
    for name in os.listdir(cache_root):
        path = os.path.join(cache_root, name)
        if os.path.isfile(path):
            os.remove(path)
    try:
        os.rmdir(cache_root)
    except OSError:
        pass


def delete_stored_file(file_record: File) -> None:
    if file_record.storage_backend == "gcs" and file_record.gcs_uri:
        try:
            gcs.delete_user_file(file_record.gcs_uri)
        except Exception:
            pass
        if file_record.extracted_gcs_uri:
            try:
                gcs.delete_user_file(file_record.extracted_gcs_uri)
            except Exception:
                pass
        cleanup_temp_cache(file_record)
        return

    if os.path.isfile(file_record.path):
        os.remove(file_record.path)
    sidecar = extracted_local_path(file_record.path)
    if os.path.isfile(sidecar):
        os.remove(sidecar)
