"""Encryption at rest for third-party API keys (basemap keys and similar)."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    secret = settings.FIELD_ENCRYPTION_KEY or settings.SECRET_KEY
    # Derive a Fernet key (32 url-safe base64 bytes) from the configured secret.
    digest = hashlib.sha256(("spatial-field-encryption:" + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        # The encryption secret changed since the key was saved.
        raise ValueError("Stored API key can't be read; enter it again.") from None
