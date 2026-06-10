"""OpenAI Whisper transcription for worker voice input."""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

logger = logging.getLogger("baupass.ai.whisper")


def _parse_openai_http_error(detail: str) -> dict[str, Any]:
    """Map OpenAI HTTP error bodies to stable BauPass error codes."""
    text = (detail or "").strip()
    if not text:
        return {"error": "whisper_http_error", "hint": "Transcription failed."}

    payload: dict[str, Any] | None = None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            payload = parsed
    except json.JSONDecodeError:
        payload = None

    err = payload.get("error") if isinstance(payload, dict) else {}
    if not isinstance(err, dict):
        err = {}
    oai_code = str(err.get("code") or err.get("type") or "").strip()
    message = str(err.get("message") or "")

    if oai_code == "insufficient_quota" or "insufficient_quota" in text or "exceeded your current quota" in message:
        return {
            "error": "openai_quota_exceeded",
            "hint": "OpenAI quota exceeded — add billing at platform.openai.com/settings/billing.",
        }
    if oai_code in {"invalid_api_key", "authentication_error"} or "invalid api key" in message.lower():
        return {"error": "openai_auth_error", "hint": "Invalid OPENAI_API_KEY on the server."}
    if oai_code == "rate_limit_exceeded":
        return {"error": "openai_rate_limit", "hint": "OpenAI rate limit — try again in a moment."}
    if message:
        return {"error": "whisper_http_error", "hint": message[:300]}
    return {"error": "whisper_http_error", "hint": text[:300]}


def transcribe_audio_bytes(
    audio_bytes: bytes,
    *,
    filename: str = "audio.webm",
    mime: str = "audio/webm",
    language: str | None = None,
) -> dict[str, Any]:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return {"text": None, "error": "openai_not_configured"}
    if not audio_bytes or len(audio_bytes) < 500:
        return {"text": None, "error": "audio_too_short"}

    boundary = f"----Baupass{uuid.uuid4().hex}"
    model = (os.getenv("BAUPASS_WHISPER_MODEL") or "whisper-1").strip()
    lang = (language or os.getenv("BAUPASS_WHISPER_LANG") or "").strip()[:2]
    auto_lang = not lang or lang.lower() in {"auto", "mul", "*", "xx"}

    parts: list[bytes] = []
    crlf = b"\r\n"

    def add_field(name: str, value: str) -> None:
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(value.encode())

    add_field("model", model)
    if not auto_lang:
        add_field("language", lang)
    parts.append(f"--{boundary}".encode())
    parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode())
    parts.append(f"Content-Type: {mime}".encode())
    parts.append(b"")
    parts.append(audio_bytes)
    parts.append(f"--{boundary}--".encode())
    parts.append(b"")

    body = crlf.join(parts)
    req = urlrequest.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (data.get("text") or "").strip()
        if not text or len(text) < 2:
            return {"text": None, "error": "no_speech_detected"}
        if all(ch in ".,;:!?…-–—'\"` " for ch in text):
            return {"text": None, "error": "no_speech_detected"}
        return {"text": text, "model": model}
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        logger.warning("Whisper HTTP %s: %s", exc.code, detail)
        parsed = _parse_openai_http_error(detail)
        return {"text": None, **parsed}
    except Exception as exc:
        return {"text": None, "error": "whisper_failed", "hint": str(exc)[:300]}
