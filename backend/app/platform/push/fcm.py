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
    return bool(os.getenv("FCM_SERVER_KEY", "").strip() or os.getenv("FIREBASE_SERVER_KEY", "").strip())


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
    key = _server_key()
    clean = [t.strip() for t in tokens if t and str(t).strip()]
    if not key or not clean:
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
