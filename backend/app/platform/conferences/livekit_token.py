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
    name: str = "",
    room: str = "",
    ttl_seconds: int = 7200,
    can_publish: bool = True,
    can_subscribe: bool = True,
    can_publish_data: bool = True,
    room_join: bool = True,
    room_list: bool = False,
    room_create: bool = False,
    room_admin: bool = False,
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
    if not identity:
        raise ValueError("identity required")
    if room_join and not room:
        raise ValueError("identity and room required when room_join")

    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    video_grant: dict[str, Any] = {}
    if room_join:
        video_grant["roomJoin"] = True
        video_grant["room"] = room
        video_grant["canPublish"] = can_publish
        video_grant["canSubscribe"] = can_subscribe
        video_grant["canPublishData"] = can_publish_data
    if room_list:
        video_grant["roomList"] = True
    if room_create:
        video_grant["roomCreate"] = True
    if room_admin:
        video_grant["roomAdmin"] = True
        if room:
            video_grant["room"] = room

    payload: dict[str, Any] = {
        "exp": now + max(60, int(ttl_seconds)),
        "iss": api_key,
        "nbf": now - 10,
        "sub": identity,
        "video": video_grant,
    }
    display = str(name or "").strip()
    if display:
        payload["name"] = display

    h = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h}.{p}".encode("utf-8")
    sig = hmac.new(api_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"
