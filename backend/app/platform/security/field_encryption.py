"""
Field-level encryption for sensitive document payloads.
Set BAUPASS_FIELD_ENCRYPTION_KEY (Fernet key or 32+ byte secret).
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet | None:
    raw = os.getenv("BAUPASS_FIELD_ENCRYPTION_KEY", "").strip()
    if not raw:
        return None
    try:
        return Fernet(raw.encode())
    except Exception:
        digest = hashlib.sha256(raw.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(plain: str) -> str:
    f = _fernet()
    if not f:
        return plain
    return f.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_text(cipher: str) -> str:
    f = _fernet()
    if not f:
        return cipher
    return f.decrypt(cipher.encode("ascii")).decode("utf-8")
