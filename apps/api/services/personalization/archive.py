from __future__ import annotations

import os
from datetime import date
from typing import Any, Protocol

from config import settings
from services.personalization.archive_crypto import (
    decrypt_payload,
    encrypt_payload,
    pack_records_jsonl,
    unpack_records_jsonl,
)


def object_key_for_period(workspace_id: str, period_start: date) -> str:
    return (
        f"{workspace_id}/{period_start.year}/"
        f"{period_start.month:02d}/{period_start.day:02d}.jsonl.gz.enc"
    )


class PromptArchive(Protocol):
    def upload_period(
        self, workspace_id: str, period_start: date, records: list[dict[str, Any]]
    ) -> str: ...

    def download_period(
        self, workspace_id: str, period_start: date
    ) -> list[dict[str, Any]]: ...

    def object_exists(self, workspace_id: str, period_start: date) -> bool: ...


class _BasePromptArchive:
    def __init__(self, bucket: str) -> None:
        self.bucket = bucket

    def _encrypt_records(self, records: list[dict[str, Any]]) -> bytes:
        packed = pack_records_jsonl(records)
        return encrypt_payload(settings.personalization_archive_key, packed)

    def _decrypt_records(self, blob: bytes) -> list[dict[str, Any]]:
        packed = decrypt_payload(settings.personalization_archive_key, blob)
        return unpack_records_jsonl(packed)

    def object_key(self, workspace_id: str, period_start: date) -> str:
        return object_key_for_period(workspace_id, period_start)


class GcsPromptArchive(_BasePromptArchive):
    def __init__(self, bucket: str) -> None:
        super().__init__(bucket)
        creds = settings.google_application_credentials.strip()
        if creds:
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", creds)
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-storage is required for GCS archive "
                "(pip install google-cloud-storage)"
            ) from exc
        self._client = storage.Client()

    def upload_period(
        self, workspace_id: str, period_start: date, records: list[dict[str, Any]]
    ) -> str:
        key = self.object_key(workspace_id, period_start)
        blob = self._client.bucket(self.bucket).blob(key)
        blob.upload_from_string(
            self._encrypt_records(records),
            content_type="application/octet-stream",
        )
        return f"gs://{self.bucket}/{key}"

    def download_period(
        self, workspace_id: str, period_start: date
    ) -> list[dict[str, Any]]:
        key = self.object_key(workspace_id, period_start)
        blob = self._client.bucket(self.bucket).blob(key)
        if not blob.exists():
            return []
        return self._decrypt_records(blob.download_as_bytes())

    def object_exists(self, workspace_id: str, period_start: date) -> bool:
        key = self.object_key(workspace_id, period_start)
        return self._client.bucket(self.bucket).blob(key).exists()


class S3PromptArchive(_BasePromptArchive):
    def __init__(self, bucket: str) -> None:
        super().__init__(bucket)
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for S3 archive (pip install boto3)"
            ) from exc
        self._client = boto3.client("s3", region_name=settings.aws_region or None)

    def upload_period(
        self, workspace_id: str, period_start: date, records: list[dict[str, Any]]
    ) -> str:
        key = self.object_key(workspace_id, period_start)
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=self._encrypt_records(records),
            ContentType="application/octet-stream",
        )
        return f"s3://{self.bucket}/{key}"

    def download_period(
        self, workspace_id: str, period_start: date
    ) -> list[dict[str, Any]]:
        from botocore.exceptions import ClientError

        key = self.object_key(workspace_id, period_start)
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404", "NotFound"}:
                return []
            raise
        return self._decrypt_records(response["Body"].read())

    def object_exists(self, workspace_id: str, period_start: date) -> bool:
        from botocore.exceptions import ClientError

        key = self.object_key(workspace_id, period_start)
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise


def archive_is_configured() -> bool:
    if not settings.cloud_archive_enabled:
        return False
    if not settings.personalization_archive_key.strip():
        return False
    provider = settings.cloud_archive_provider.strip().lower()
    if provider == "gcs":
        return bool(settings.gcs_archive_bucket.strip())
    if provider == "s3":
        return bool(settings.s3_archive_bucket.strip())
    return False


def get_prompt_archive() -> PromptArchive:
    provider = settings.cloud_archive_provider.strip().lower()
    if provider == "gcs":
        bucket = settings.gcs_archive_bucket.strip()
        if not bucket:
            raise ValueError("GCS_ARCHIVE_BUCKET is required when CLOUD_ARCHIVE_PROVIDER=gcs")
        return GcsPromptArchive(bucket)
    if provider == "s3":
        bucket = settings.s3_archive_bucket.strip()
        if not bucket:
            raise ValueError("S3_ARCHIVE_BUCKET is required when CLOUD_ARCHIVE_PROVIDER=s3")
        return S3PromptArchive(bucket)
    raise ValueError(f"Unsupported CLOUD_ARCHIVE_PROVIDER: {provider}")
