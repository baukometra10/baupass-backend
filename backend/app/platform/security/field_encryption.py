"""Optional at-rest field encryption (Fernet) for sensitive text columns."""
from __future__ import annotations

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("baupass.field_encryption")

_PREFIX = "enc:v1:"
_fernet: Fernet | None | bool = False


def _get_fernet() -> Fernet | None:
    global _fernet
    if _fernet is False:
        raw = (
            os.getenv("BAUPASS_FIELD_ENCRYPTION_KEY", "").strip()
            or os.getenv("SUPPIX_FIELD_ENCRYPTION_KEY", "").strip()
        )
        if not raw:
            _fernet = None
        else:
            try:
                if len(raw) == 44 and raw.endswith("="):
                    key = raw.encode("ascii")
                else:
                    digest = hashlib.sha256(raw.encode("utf-8")).digest()
                    key = base64.urlsafe_b64encode(digest)
                _fernet = Fernet(key)
            except Exception as exc:
                logger.error("Invalid field encryption key: %s", exc)
                _fernet = None
    return _fernet if _fernet is not False else None


def field_encryption_enabled() -> bool:
    return _get_fernet() is not None


def maybe_encrypt_field(value: str) -> str:
    text = str(value or "")
    if not text or text.startswith(_PREFIX):
        return text
    fernet = _get_fernet()
    if not fernet:
        return text
    token = fernet.encrypt(text.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def maybe_decrypt_field(value: str) -> str:
    text = str(value or "")
    if not text.startswith(_PREFIX):
        return text
    fernet = _get_fernet()
    if not fernet:
        return text
    try:
        payload = text[len(_PREFIX) :].encode("ascii")
        return fernet.decrypt(payload).decode("utf-8")
    except InvalidToken:
        logger.warning("Failed to decrypt field (invalid token)")
        return text
    except Exception as exc:
        logger.warning("Failed to decrypt field: %s", exc)
        return text
