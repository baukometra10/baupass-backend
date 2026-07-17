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
    """Mint a LiveKit access token compatible with LiveKit Cloud / open-source SFU.

    Claim shape mirrors livekit-api AccessToken (camelCase video grants).
    """
    api_key = str(api_key or "").strip()
    api_secret = str(api_secret or "").strip()
    identity = str(identity or "").strip()
    room = str(room or "").strip()
    if not api_key or not api_secret:
        raise ValueError("api_key and api_secret required")
    if not identity or not room:
        raise ValueError("identity and room required")

    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    video_grant: dict[str, Any] = {
        "roomJoin": True,
        "room": room,
        "canPublish": can_publish,
        "canSubscribe": can_subscribe,
        "canPublishData": can_publish_data,
    }
    # Keep payload minimal (official SDK drops empty strings / None).
    payload: dict[str, Any] = {
        "iss": api_key,
        "sub": identity,
        "nbf": now - 10,
        "exp": now + max(60, int(ttl_seconds)),
        "video": video_grant,
    }
    display = str(name or "").strip()
    if display:
        payload["name"] = display

    # Do not sort_keys — match typical PyJWT serialization order expectations.
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    sig = hmac.new(api_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"
