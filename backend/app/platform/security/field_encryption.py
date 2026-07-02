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


def maybe_encrypt_field(value: str, *, company_id: str = "") -> str:
    text = str(value or "")
    if not text or text.startswith(_PREFIX) or text.startswith(_PREFIX_V2):
        return text
    if company_id:
        return encrypt_chat_field(str(company_id), text)
    fernet = _get_fernet()
    if not fernet:
        return text
    token = fernet.encrypt(text.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def maybe_decrypt_field(value: str, *, company_id: str = "") -> str:
    text = str(value or "")
    if text.startswith(_PREFIX_V2):
        if company_id:
            return decrypt_chat_field(str(company_id), text)
        return text
    if text.startswith(_PREFIX):
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
    return text


_PREFIX_V2 = "enc:v2:"


def _company_fernet(company_id: str) -> Fernet | None:
    raw = (
        os.getenv("BAUPASS_FIELD_ENCRYPTION_KEY", "").strip()
        or os.getenv("SUPPIX_FIELD_ENCRYPTION_KEY", "").strip()
    )
    if not raw or not str(company_id or "").strip():
        return None
    try:
        seed = hashlib.sha256(f"chat:{raw}:{company_id}".encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(seed)
        return Fernet(key)
    except Exception as exc:
        logger.error("Invalid company-scoped encryption: %s", exc)
        return None


def encrypt_chat_field(company_id: str, plaintext: str) -> str:
    text = str(plaintext or "")
    if not text or text.startswith(_PREFIX_V2):
        return text
    fernet = _company_fernet(company_id)
    if not fernet:
        return maybe_encrypt_field(text)
    token = fernet.encrypt(text.encode("utf-8")).decode("ascii")
    return f"{_PREFIX_V2}{token}"


def decrypt_chat_field(company_id: str, stored: str) -> str:
    text = str(stored or "")
    if not text.startswith(_PREFIX_V2):
        return maybe_decrypt_field(text, company_id=company_id)
    fernet = _company_fernet(company_id)
    if not fernet:
        return text
    try:
        payload = text[len(_PREFIX_V2) :].encode("ascii")
        return fernet.decrypt(payload).decode("utf-8")
    except InvalidToken:
        logger.warning("Failed to decrypt chat field for company %s", company_id)
        return text
    except Exception as exc:
        logger.warning("Failed to decrypt chat field: %s", exc)
        return text
