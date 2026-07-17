"""LiveKit access token helper (HS256 JWT, no livekit SDK required)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def create_livekit_token(
    *,
    api_key: str,
    api_secret: str,
    identity: str,
    name: str,
    room: str,
    ttl_seconds: int = 7200,
    can_publish: bool = True,
    can_subscribe: bool = True,
    can_publish_data: bool = True,
) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    video_grant: dict[str, Any] = {
        "roomJoin": True,
        "room": room,
        "canPublish": can_publish,
        "canSubscribe": can_subscribe,
        "canPublishData": can_publish_data,
    }
    payload = {
        "iss": api_key,
        "sub": identity,
        "nbf": now - 10,
        "exp": now + max(60, ttl_seconds),
        "name": name,
        "video": video_grant,
        "metadata": "",
    }
    h = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{h}.{p}".encode()
    sig = hmac.new(api_secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"
