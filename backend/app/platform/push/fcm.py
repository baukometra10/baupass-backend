"""Firebase Cloud Messaging (legacy HTTP API) for worker native apps."""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_FCM_URL = "https://fcm.googleapis.com/fcm/send"


def fcm_configured() -> bool:
    if os.getenv("FCM_SERVER_KEY", "").strip() or os.getenv("FIREBASE_SERVER_KEY", "").strip():
        return True
    try:
        from .fcm_v1 import fcm_v1_configured

        return fcm_v1_configured()
    except Exception:
        return False


def fcm_v1_only() -> bool:
    return os.getenv("FCM_V1_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}


def fcm_mode() -> str:
    try:
        from .fcm_v1 import fcm_v1_configured

        if fcm_v1_configured():
            return "http_v1"
    except Exception:
        pass
    if fcm_v1_only():
        return "none"
    if _server_key():
        return "legacy"
    return "none"


def _server_key() -> str:
    return (os.getenv("FCM_SERVER_KEY") or os.getenv("FIREBASE_SERVER_KEY") or "").strip()


def send_fcm_notification(
    tokens: list[str],
    *,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> int:
    """Send to one or more FCM registration tokens. Returns success count."""
    clean = [t.strip() for t in tokens if t and str(t).strip()]
    if not clean:
        return 0

    try:
        from .fcm_v1 import fcm_v1_configured, send_fcm_v1

        if fcm_v1_configured():
            sent = send_fcm_v1(clean, title=title, body=body, data=data)
            if sent > 0 or fcm_v1_only():
                return sent
    except Exception as exc:
        logger.warning("FCM v1 path failed: %s", exc)
        if fcm_v1_only():
            return 0

    if fcm_v1_only():
        return 0

    key = _server_key()
    if not key:
        return 0

    payload: dict[str, Any] = {
        "registration_ids": clean[:500],
        "notification": {"title": title[:200], "body": body[:500]},
        "priority": "high",
    }
    if data:
        payload["data"] = {str(k): str(v)[:200] for k, v in data.items()}

    req = urllib.request.Request(
        _FCM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"key={key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        result = json.loads(raw) if raw else {}
        success = int(result.get("success") or 0)
        failure = int(result.get("failure") or 0)
        if failure and success == 0:
            logger.warning("FCM all failed: %s", raw[:300])
        return success
    except urllib.error.HTTPError as exc:
        logger.warning("FCM HTTP %s: %s", exc.code, exc.read()[:200])
    except Exception as exc:
        logger.warning("FCM send failed: %s", exc)
    return 0
