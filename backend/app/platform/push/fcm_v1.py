"""FCM HTTP v1 (service account) — optional upgrade from legacy server key."""
from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)

_TOKEN_CACHE: dict[str, Any] = {"token": None, "exp": 0}


def fcm_v1_configured() -> bool:
    return bool(_project_id() and _load_service_account())


def _project_id() -> str:
    return (os.getenv("FCM_PROJECT_ID") or os.getenv("FIREBASE_PROJECT_ID") or "").strip()


def _load_service_account() -> dict[str, Any] | None:
    raw = (os.getenv("FCM_SERVICE_ACCOUNT_JSON") or "").strip()
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    b64 = (os.getenv("FCM_SERVICE_ACCOUNT_B64") or "").strip()
    if b64:
        try:
            return json.loads(base64.b64decode(b64))
        except Exception:
            return None
    path = (os.getenv("FCM_SERVICE_ACCOUNT_PATH") or "").strip()
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None
    return None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _service_account_token(sa: dict[str, Any]) -> str | None:
    now = int(time.time())
    if _TOKEN_CACHE.get("token") and int(_TOKEN_CACHE.get("exp") or 0) > now + 60:
        return str(_TOKEN_CACHE["token"])

    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claim = _b64url(
        json.dumps(
            {
                "iss": sa["client_email"],
                "scope": "https://www.googleapis.com/auth/firebase.messaging",
                "aud": "https://oauth2.googleapis.com/token",
                "iat": now,
                "exp": now + 3600,
            },
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{claim}".encode("ascii")
    key = serialization.load_pem_private_key(sa["private_key"].encode("utf-8"), password=None)
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    jwt = f"{header}.{claim}.{_b64url(signature)}"

    body = urllib.parse.urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        token = str(data.get("access_token") or "")
        if not token:
            return None
        _TOKEN_CACHE["token"] = token
        _TOKEN_CACHE["exp"] = now + int(data.get("expires_in") or 3600)
        return token
    except Exception as exc:
        logger.warning("FCM v1 OAuth failed: %s", exc)
        return None


def send_fcm_v1(tokens: list[str], *, title: str, body: str, data: dict[str, Any] | None = None) -> int:
    """Send via FCM HTTP v1; one request per token."""
    sa = _load_service_account()
    project = _project_id()
    if not sa or not project:
        return 0
    access = _service_account_token(sa)
    if not access:
        return 0

    success = 0
    url = f"https://fcm.googleapis.com/v1/projects/{project}/messages:send"
    for token in tokens[:200]:
        message: dict[str, Any] = {
            "message": {
                "token": token,
                "notification": {"title": title[:200], "body": body[:500]},
                "android": {"priority": "HIGH"},
            }
        }
        if data:
            message["message"]["data"] = {str(k): str(v)[:200] for k, v in data.items()}
        req = urllib.request.Request(
            url,
            data=json.dumps(message).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {access}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                if 200 <= resp.status < 300:
                    success += 1
        except urllib.error.HTTPError as exc:
            logger.warning("FCM v1 HTTP %s: %s", exc.code, exc.read()[:160])
        except Exception as exc:
            logger.warning("FCM v1 send failed: %s", exc)
    return success
