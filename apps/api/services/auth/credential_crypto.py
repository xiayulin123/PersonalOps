"""Encrypt/decrypt per-user API credentials at rest."""

from __future__ import annotations

from base64 import urlsafe_b64encode
from hashlib import sha256

from cryptography.fernet import Fernet, InvalidToken

from config import settings


def _fernet() -> Fernet:
    secret = (
        getattr(settings, "credentials_encryption_key", "") or settings.jwt_secret
    ).strip()
    if not secret:
        raise ValueError(
            "CREDENTIALS_ENCRYPTION_KEY or JWT_SECRET is required to store user API keys"
        )
    key = urlsafe_b64encode(sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    token = _fernet().encrypt(plain.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(encrypted: str) -> str:
    try:
        return _fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Credential decryption failed — wrong encryption key?") from exc
