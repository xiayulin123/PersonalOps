"""Numeric email verification codes (register + password reset)."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from config import settings


def generate_numeric_code(length: int = 6) -> str:
    upper = 10**length
    return f"{secrets.randbelow(upper):0{length}d}"


def _code_secret() -> str:
    secret = (
        settings.jwt_secret.strip()
        or settings.credentials_encryption_key.strip()
        or "dev-email-code-secret"
    )
    return secret


def hash_code(code: str) -> str:
    normalized = code.strip()
    return hmac.new(
        _code_secret().encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_code(code: str, code_hash: str) -> bool:
    try:
        return hmac.compare_digest(hash_code(code), code_hash)
    except ValueError:
        return False
