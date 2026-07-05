"""Detect and validate client-side E2E envelopes (server never decrypts content)."""
from __future__ import annotations

import json
import re
from typing import Any

_E2E_MARKERS = frozenset({"e2e", "multi", "ratchet"})
_ALLOWED_ALGS = frozenset({"X25519-AES-GCM", "X25519-AES-GCM-RATCHET"})
_ATTACHMENT_KINDS = frozenset({"attachment", "field"})


def _parse_envelope(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw.startswith("{"):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def is_e2e_envelope(value: str) -> bool:
    parsed = _parse_envelope(value)
    if not parsed:
        return False
    if parsed.get("e2e") is True and parsed.get("v") in (1, 2) and parsed.get("ct"):
        alg = str(parsed.get("alg") or "X25519-AES-GCM")
        return alg in _ALLOWED_ALGS
    if parsed.get("e2e") is True and parsed.get("multi") is True and isinstance(parsed.get("envelopes"), list):
        envelopes = parsed.get("envelopes") or []
        return bool(envelopes) and all(is_e2e_envelope(json.dumps(item, separators=(",", ":"))) for item in envelopes if isinstance(item, dict))
    return False


def is_e2e_attachment_meta(value: str) -> bool:
    parsed = _parse_envelope(value)
    if not parsed or parsed.get("e2e") is not True:
        return False
    kind = str(parsed.get("kind") or "").strip().lower()
    if kind != "attachment":
        return False
    has_key = bool(parsed.get("wrappedKey")) or bool(parsed.get("keyEnvelopes"))
    return bool(parsed.get("iv")) and has_key


def assert_e2e_message_body(body: str) -> None:
    if not is_e2e_envelope(body):
        raise ValueError("e2e_required")


def assert_e2e_attachment(*, e2e_meta: str, content_type: str, encrypted: bool) -> None:
    if not is_e2e_attachment_meta(e2e_meta):
        raise ValueError("e2e_attachment_required")
    ct = str(content_type or "").lower()
    if encrypted and ct not in {"application/octet-stream", "application/vnd.suppix.e2e+binary"}:
        raise ValueError("e2e_attachment_content_type_invalid")


def assert_e2e_sensitive_field(value: str, *, field_name: str = "field") -> None:
    text = str(value or "").strip()
    if not text:
        return
    if not is_e2e_envelope(text):
        raise ValueError(f"e2e_required_{field_name}")
