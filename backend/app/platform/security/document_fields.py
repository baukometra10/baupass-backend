"""
Encrypt sensitive worker document metadata when BAUPASS_FIELD_ENCRYPTION_KEY is set.
"""
from __future__ import annotations

import os

from .field_encryption import decrypt_text, encrypt_text

SENSITIVE_PREFIX = "enc:"


def maybe_encrypt_field(value: str | None) -> str:
    if not value or not os.getenv("BAUPASS_FIELD_ENCRYPTION_KEY", "").strip():
        return value or ""
    if str(value).startswith(SENSITIVE_PREFIX):
        return str(value)
    return SENSITIVE_PREFIX + encrypt_text(str(value))


def maybe_decrypt_field(value: str | None) -> str:
    if not value:
        return ""
    raw = str(value)
    if not raw.startswith(SENSITIVE_PREFIX):
        return raw
    try:
        return decrypt_text(raw[len(SENSITIVE_PREFIX) :])
    except Exception:
        return raw
