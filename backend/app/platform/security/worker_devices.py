"""Worker mobile device binding and signed JWT access tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any


def worker_device_binding_enabled() -> bool:
    raw = (os.getenv("BAUPASS_WORKER_DEVICE_BINDING") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def worker_jwt_enabled() -> bool:
    raw = (os.getenv("BAUPASS_WORKER_JWT") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _jwt_secret() -> str:
    explicit = (os.getenv("BAUPASS_WORKER_JWT_SECRET") or "").strip()
    if explicit:
        return explicit
    fallback = (os.getenv("BAUPASS_DQR_SECRET") or os.getenv("BAUPASS_IDENTITY_TOKEN_SECRET") or "").strip()
    if fallback:
        return fallback
    return "baupass-worker-jwt-dev-only-change-me"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def issue_worker_access_jwt(
    *,
    worker_id: str,
    device_id: str,
    session_token: str,
    expires_at_iso: str,
) -> str:
    """Return HS256 JWT bound to worker session + device."""
    try:
        from datetime import datetime

        exp_ts = int(datetime.fromisoformat(expires_at_iso.replace("Z", "+00:00")).timestamp())
    except Exception:
        exp_ts = int(time.time()) + 86400

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": worker_id,
        "did": device_id or "",
        "sid": session_token,
        "typ": "worker",
        "iat": int(time.time()),
        "exp": exp_ts,
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(_jwt_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def verify_worker_access_jwt(token: str) -> dict[str, Any] | None:
    parts = str(token or "").split(".")
    if len(parts) != 3:
        return None
    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        if header.get("alg") != "HS256" or payload.get("typ") != "worker":
            return None
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(_jwt_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
        provided = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected, provided):
            return None
        exp = int(payload.get("exp") or 0)
        if exp and exp < int(time.time()):
            return None
        worker_id = str(payload.get("sub") or "").strip()
        session_token = str(payload.get("sid") or "").strip()
        if not worker_id or not session_token:
            return None
        return {
            "worker_id": worker_id,
            "device_id": str(payload.get("did") or "").strip(),
            "session_token": session_token,
        }
    except Exception:
        return None


def looks_like_jwt(token: str) -> bool:
    parts = str(token or "").split(".")
    return len(parts) == 3 and parts[0].startswith("eyJ")


def normalize_device_fingerprint(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) > 120:
        raw = raw[:120]
    return raw


def bind_worker_device(db, worker_row, device_payload: dict[str, Any] | None, session_token: str) -> dict[str, Any]:
    """Register or refresh a worker device and link it to the active session."""
    payload = device_payload if isinstance(device_payload, dict) else {}
    fingerprint = normalize_device_fingerprint(
        payload.get("fingerprint") or payload.get("deviceFingerprint") or payload.get("deviceId")
    )
    if not fingerprint:
        return {"deviceId": "", "bound": False}

    device_name = str(payload.get("name") or payload.get("deviceName") or "Mobile").strip()[:120]
    platform = str(payload.get("platform") or payload.get("deviceType") or "unknown").strip()[:40]
    push_token = str(payload.get("pushToken") or payload.get("deviceToken") or "").strip()[:512]

    existing = db.execute(
        """
        SELECT id, status
        FROM worker_bound_devices
        WHERE worker_id = ? AND device_fingerprint = ?
        LIMIT 1
        """,
        (worker_row["id"], fingerprint),
    ).fetchone()

    now_value = time.strftime("%Y-%m-%dT%H:%M:%S")
    if existing:
        device_id = existing["id"]
        db.execute(
            """
            UPDATE worker_bound_devices
            SET device_name = ?, platform = ?, push_token = ?, last_seen_at = ?, status = 'active'
            WHERE id = ?
            """,
            (device_name, platform, push_token, now_value, device_id),
        )
    else:
        device_id = f"wbd-{secrets.token_hex(10)}"
        db.execute(
            """
            INSERT INTO worker_bound_devices (
                id, worker_id, company_id, device_fingerprint, device_name, platform,
                push_token, status, created_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                device_id,
                worker_row["id"],
                worker_row["company_id"],
                fingerprint,
                device_name,
                platform,
                push_token,
                now_value,
                now_value,
            ),
        )

    db.execute(
        "UPDATE worker_app_sessions SET bound_device_id = ? WHERE token = ?",
        (device_id, session_token),
    )
    return {"deviceId": device_id, "bound": True, "fingerprint": fingerprint}


def validate_bound_device_for_request(db, worker_id: str, session_token: str, request_device_id: str) -> tuple[bool, str]:
    """Return (ok, error_code). Skips when binding disabled or session has no bound device."""
    if not worker_device_binding_enabled():
        return True, ""
    header_device_id = str(request_device_id or "").strip()
    session_row = db.execute(
        "SELECT bound_device_id FROM worker_app_sessions WHERE token = ? AND worker_id = ?",
        (session_token, worker_id),
    ).fetchone()
    bound_device_id = str((session_row["bound_device_id"] if session_row else "") or "").strip()
    if not bound_device_id:
        return True, ""
    if not header_device_id:
        return False, "missing_device_id"
    if header_device_id != bound_device_id:
        return False, "device_not_bound"
    device_row = db.execute(
        """
        SELECT status FROM worker_bound_devices
        WHERE id = ? AND worker_id = ?
        LIMIT 1
        """,
        (bound_device_id, worker_id),
    ).fetchone()
    if not device_row or str(device_row["status"] or "") != "active":
        return False, "device_not_active"
    return True, ""
