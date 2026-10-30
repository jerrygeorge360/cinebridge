from __future__ import annotations

import hashlib
import hmac
import os
import secrets


TOKEN_DIGEST_VERSION = "v1"
TOKEN_BYTES = 32
_development_digest_secret = secrets.token_bytes(32)


def _digest_secret() -> bytes:
    configured = os.getenv("TOKEN_DIGEST_SECRET")
    if configured:
        return configured.encode("utf-8")
    if os.getenv("ENVIRONMENT", "development").lower() in {"production", "prod"}:
        raise RuntimeError("TOKEN_DIGEST_SECRET must be configured in production")
    return _development_digest_secret


def generate_access_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def digest_token(token: str, purpose: str) -> str:
    material = f"{TOKEN_DIGEST_VERSION}:{purpose}:{token}".encode("utf-8")
    return hmac.new(_digest_secret(), material, hashlib.sha256).hexdigest()


def token_matches(token: str, purpose: str, stored_digest: str) -> bool:
    return hmac.compare_digest(digest_token(token, purpose), stored_digest)


def rate_limit_key(source: str, token_digest: str | None = None) -> str:
    material = source if token_digest is None else f"{source}:{token_digest}"
    return hmac.new(_digest_secret(), material.encode("utf-8"), hashlib.sha256).hexdigest()


def validate_runtime_configuration() -> None:
    _digest_secret()


__all__ = [
    "TOKEN_BYTES",
    "TOKEN_DIGEST_VERSION",
    "digest_token",
    "generate_access_token",
    "rate_limit_key",
    "token_matches",
    "validate_runtime_configuration",
]
