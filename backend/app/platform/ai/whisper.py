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
    if not audio_bytes or len(audio_bytes) < 100:
        return {"text": None, "error": "audio_too_short"}

    boundary = f"----Baupass{uuid.uuid4().hex}"
    model = (os.getenv("BAUPASS_WHISPER_MODEL") or "whisper-1").strip()
    lang = (language or os.getenv("BAUPASS_WHISPER_LANG") or "").strip()[:2]

    parts: list[bytes] = []
    crlf = b"\r\n"

    def add_field(name: str, value: str) -> None:
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(value.encode())

    add_field("model", model)
    if lang:
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
        return {"text": (data.get("text") or "").strip(), "model": model}
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        logger.warning("Whisper HTTP %s: %s", exc.code, detail)
        return {"text": None, "error": "whisper_http_error", "hint": detail}
    except Exception as exc:
        return {"text": None, "error": "whisper_failed", "hint": str(exc)[:300]}
