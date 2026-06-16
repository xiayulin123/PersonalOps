"""GCS app storage helpers (Plan B B2/B3)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from config import settings
from services.auth.credential_crypto import encrypt_secret
from services.deployment import is_cloud_deployment


def is_gcs_app_storage_enabled() -> bool:
    if not settings.gcs_storage_enabled:
        return False
    if not (settings.gcs_app_bucket or settings.gcs_archive_bucket).strip():
        return False
    if not is_cloud_deployment():
        return False
    return True


def _bucket_name() -> str:
    bucket = (settings.gcs_app_bucket or settings.gcs_archive_bucket).strip()
    if not bucket:
        raise ValueError("GCS_APP_BUCKET or GCS_ARCHIVE_BUCKET is required")
    return bucket


def user_prefix(user_id: str) -> str:
    return f"users/{user_id}"


def workspace_upload_prefix(user_id: str, workspace_id: str) -> str:
    return f"{user_prefix(user_id)}/workspaces/{workspace_id}/uploads"


def upload_object_path(
    user_id: str,
    workspace_id: str,
    file_id: str,
    filename: str,
) -> str:
    safe_name = filename.replace("/", "_")
    return f"{workspace_upload_prefix(user_id, workspace_id)}/{file_id}/{safe_name}"


def credentials_object_path(user_id: str) -> str:
    return f"{user_prefix(user_id)}/secrets/credentials.enc"


def conversation_object_path(
    user_id: str,
    workspace_id: str,
    conversation_id: str,
) -> str:
    return (
        f"{user_prefix(user_id)}/workspaces/{workspace_id}/conversations/"
        f"{conversation_id}.jsonl"
    )


def conversation_export_prefix(user_id: str) -> str:
    return f"{user_prefix(user_id)}/workspaces/"


def parse_gs_uri(gcs_uri: str) -> tuple[str, str]:
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    remainder = gcs_uri[5:]
    bucket, _, blob_path = remainder.partition("/")
    if not bucket or not blob_path:
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    return bucket, blob_path


def _gcs_client():
    from google.cloud import storage

    creds = settings.google_application_credentials.strip()
    if creds:
        return storage.Client.from_service_account_json(creds)
    return storage.Client()


def gcs_connection_ok() -> tuple[bool, str]:
    bucket = (settings.gcs_app_bucket or settings.gcs_archive_bucket).strip()
    if not bucket:
        return False, "GCS bucket not configured"
    try:
        client = _gcs_client()
        client.get_bucket(bucket)
        return True, bucket
    except Exception as exc:
        return False, str(exc)


def check_gcs_connection() -> tuple[bool, str]:
    """Write/read/delete a health-check object in the bucket."""
    ok, detail = gcs_connection_ok()
    if not ok:
        return False, detail
    try:
        bucket_name = _bucket_name()
        client = _gcs_client()
        bucket = client.bucket(bucket_name)
        blob_path = f"system/health-check-{uuid.uuid4().hex}.txt"
        blob = bucket.blob(blob_path)
        marker = f"ok-{datetime.now(timezone.utc).isoformat()}"
        blob.upload_from_string(marker, content_type="text/plain")
        if blob.download_as_text() != marker:
            raise RuntimeError("GCS health-check read mismatch")
        blob.delete()
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def upload_user_file(
    *,
    user_id: str,
    workspace_id: str,
    file_id: str,
    filename: str,
    content: bytes,
) -> str:
    bucket_name = _bucket_name()
    object_path = upload_object_path(user_id, workspace_id, file_id, filename)
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_path)
    blob.upload_from_string(content, content_type="application/octet-stream")
    return f"gs://{bucket_name}/{object_path}"


def extracted_upload_object_path(
    user_id: str,
    workspace_id: str,
    file_id: str,
    original_filename: str,
) -> str:
    base, _ext = os.path.splitext(original_filename.replace("/", "_"))
    safe_name = f"{base}.extracted.txt"
    return f"{workspace_upload_prefix(user_id, workspace_id)}/{file_id}/{safe_name}"


def upload_extracted_text(
    *,
    user_id: str,
    workspace_id: str,
    file_id: str,
    original_filename: str,
    content: bytes,
) -> str:
    bucket_name = _bucket_name()
    object_path = extracted_upload_object_path(
        user_id, workspace_id, file_id, original_filename
    )
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_path)
    blob.upload_from_string(content, content_type="text/plain; charset=utf-8")
    return f"gs://{bucket_name}/{object_path}"


def download_user_file(gcs_uri: str, dest_path: str) -> None:
    import os

    bucket_name, blob_path = parse_gs_uri(gcs_uri)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(dest_path)


def delete_user_file(gcs_uri: str) -> None:
    bucket_name, blob_path = parse_gs_uri(gcs_uri)
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.delete()


def get_user_storage_bytes(user_id: str) -> int:
    bucket_name = _bucket_name()
    prefix = f"{user_prefix(user_id)}/"
    client = _gcs_client()
    total = 0
    for blob in client.list_blobs(bucket_name, prefix=prefix):
        total += int(blob.size or 0)
    return total


def copy_prefix(*, source_prefix: str, dest_prefix: str) -> str:
    """Copy all objects under source_prefix to dest_prefix within the app bucket."""
    bucket_name = _bucket_name()
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    copied = 0
    source = source_prefix.rstrip("/") + "/"
    dest = dest_prefix.rstrip("/") + "/"
    for blob in client.list_blobs(bucket_name, prefix=source):
        name = blob.name or ""
        if not name.startswith(source):
            continue
        relative = name[len(source) :]
        if not relative:
            continue
        target_name = f"{dest}{relative}"
        bucket.copy_blob(blob, bucket, new_name=target_name)
        copied += 1
    return f"gs://{bucket_name}/{dest} ({copied} objects)"


def count_user_conversation_exports(user_id: str) -> int:
    bucket_name = _bucket_name()
    prefix = f"{user_prefix(user_id)}/workspaces/"
    suffix = "/conversations/"
    client = _gcs_client()
    count = 0
    for blob in client.list_blobs(bucket_name, prefix=prefix):
        name = blob.name or ""
        if suffix in name and name.endswith(".jsonl"):
            count += 1
    return count


def export_conversation_jsonl(
    *,
    user_id: str,
    workspace_id: str,
    conversation_id: str,
    content: bytes,
) -> str:
    bucket_name = _bucket_name()
    object_path = conversation_object_path(user_id, workspace_id, conversation_id)
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_path)
    blob.upload_from_string(content, content_type="application/x-ndjson")
    return f"gs://{bucket_name}/{object_path}"


def download_blob_bytes(gcs_uri: str) -> bytes:
    bucket_name, blob_path = parse_gs_uri(gcs_uri)
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    return blob.download_as_bytes()


def _parse_conversation_export_path(
    object_path: str,
    *,
    expected_user_id: str,
) -> dict[str, str] | None:
    """Parse users/{uid}/workspaces/{wid}/conversations/{cid}.jsonl."""
    parts = object_path.split("/")
    try:
        user_idx = parts.index("users")
        workspace_idx = parts.index("workspaces")
        conversations_idx = parts.index("conversations")
    except ValueError:
        return None

    if conversations_idx + 1 >= len(parts):
        return None

    user_id = parts[user_idx + 1]
    workspace_id = parts[workspace_idx + 1]
    filename = parts[conversations_idx + 1]
    if user_id != expected_user_id or not filename.endswith(".jsonl"):
        return None

    return {
        "user_id": user_id,
        "workspace_id": workspace_id,
        "conversation_id": filename[: -len(".jsonl")],
    }


def iter_conversation_export_objects(
    user_id: str,
    *,
    workspace_id: str | None = None,
) -> list[dict[str, str]]:
    """List conversation JSONL exports under a user's GCS prefix."""
    bucket_name = _bucket_name()
    prefix = f"{user_prefix(user_id)}/workspaces/"
    if workspace_id:
        prefix = (
            f"{user_prefix(user_id)}/workspaces/{workspace_id}/conversations/"
        )
    client = _gcs_client()
    exports: list[dict[str, str]] = []
    for blob in client.list_blobs(bucket_name, prefix=prefix):
        name = blob.name or ""
        if "/conversations/" not in name or not name.endswith(".jsonl"):
            continue
        parsed = _parse_conversation_export_path(name, expected_user_id=user_id)
        if parsed is None:
            continue
        if workspace_id and parsed["workspace_id"] != workspace_id:
            continue
        exports.append(
            {
                **parsed,
                "gcs_uri": f"gs://{bucket_name}/{name}",
            }
        )
    return exports


def upload_user_credentials_backup(
    user_id: str,
    credentials: dict[str, str],
    *,
    email: str = "",
) -> str:
    """Upload encrypted credentials JSON to GCS for disaster recovery."""
    payload = {
        "user_id": user_id,
        "email": email,
        "providers": sorted(credentials.keys()),
        "credentials": credentials,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    plain = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    encrypted = encrypt_secret(plain.decode("utf-8")).encode("utf-8")

    bucket_name = _bucket_name()
    object_path = credentials_object_path(user_id)
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_path)
    blob.upload_from_string(encrypted, content_type="application/octet-stream")
    return f"gs://{bucket_name}/{object_path}"


def storage_status_for_user(user_id: str) -> dict[str, Any]:
    gcs_enabled = is_gcs_app_storage_enabled()
    bucket = (settings.gcs_app_bucket or settings.gcs_archive_bucket).strip()
    checked_at = datetime.now(timezone.utc).isoformat()

    if not gcs_enabled:
        return {
            "gcs_enabled": False,
            "connection_ok": False,
            "bucket": bucket or None,
            "detail": "GCS storage disabled or not in cloud deployment",
            "user_prefix": user_prefix(user_id) if user_id else None,
            "credentials_path": credentials_object_path(user_id) if user_id else None,
            "total_bytes": 0,
            "conversation_exports_count": 0,
            "last_checked_at": checked_at,
        }

    ok, detail = check_gcs_connection()
    total_bytes = 0
    conversation_exports_count = 0
    if ok and user_id:
        try:
            total_bytes = get_user_storage_bytes(user_id)
            conversation_exports_count = count_user_conversation_exports(user_id)
        except Exception as exc:
            ok = False
            detail = str(exc)

    return {
        "gcs_enabled": True,
        "connection_ok": ok,
        "bucket": bucket or None,
        "detail": detail if not ok else "ok",
        "user_prefix": user_prefix(user_id) if user_id else None,
        "credentials_path": credentials_object_path(user_id) if user_id else None,
        "total_bytes": total_bytes,
        "conversation_exports_count": conversation_exports_count,
        "last_checked_at": checked_at,
    }
