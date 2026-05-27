"""
Session device binding — ties login sessions to device fingerprints.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from flask import Request


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def fingerprint_from_request(req: Request) -> str:
    raw = (req.headers.get("X-Device-Fingerprint") or req.headers.get("User-Agent") or "unknown").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def register_session_device(db, *, token: str, user_id: str, req: Request) -> None:
    try:
        device_id = f"sdev-{uuid.uuid4().hex[:12]}"
        fp = fingerprint_from_request(req)
        now = _now_iso()
        db.execute(
            """
            INSERT INTO session_devices
                (id, session_token_hash, user_id, device_fingerprint, user_agent, ip_address, created_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                _token_hash(token),
                str(user_id),
                fp,
                (req.headers.get("User-Agent") or "")[:500],
                (req.remote_addr or "")[:64],
                now,
                now,
            ),
        )
    except Exception:
        pass


def touch_session_device(db, *, token: str) -> None:
    try:
        db.execute(
            "UPDATE session_devices SET last_seen_at = ? WHERE session_token_hash = ?",
            (_now_iso(), _token_hash(token)),
        )
    except Exception:
        pass


def session_device_allowed(db, *, token: str, req: Request) -> tuple[bool, str]:
    """When BAUPASS_ZERO_TRUST_DEVICE_BINDING=1, reject unknown fingerprints for session."""
    import os

    if os.getenv("BAUPASS_ZERO_TRUST_DEVICE_BINDING", "0").strip().lower() not in {"1", "true", "yes"}:
        return True, ""
    try:
        fp = fingerprint_from_request(req)
        row = db.execute(
            """
            SELECT device_fingerprint FROM session_devices
            WHERE session_token_hash = ?
            ORDER BY last_seen_at DESC
            LIMIT 1
            """,
            (_token_hash(token),),
        ).fetchone()
        if not row:
            return True, ""
        stored = str(row["device_fingerprint"] if hasattr(row, "__getitem__") else row[0])
        if stored and stored != fp:
            return False, "device_mismatch"
        touch_session_device(db, token=token)
        return True, ""
    except Exception:
        return True, ""
