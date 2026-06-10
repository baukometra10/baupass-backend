"""OpenAI text-to-speech for AI voice replies."""
from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from .openai_errors import OpenAiApiError, parse_openai_http_error, urlopen_with_rate_limit_retry

logger = logging.getLogger("baupass.ai.tts")


def synthesize_speech_bytes(text: str, *, lang: str = "de") -> dict[str, Any]:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return {"audio": None, "error": "openai_not_configured"}
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned or len(cleaned) < 2:
        return {"audio": None, "error": "text_too_short"}

    model = (os.getenv("BAUPASS_TTS_MODEL") or "tts-1").strip()
    voice = (os.getenv("BAUPASS_TTS_VOICE") or "nova").strip()
    payload = json.dumps(
        {
            "model": model,
            "input": cleaned[:4096],
            "voice": voice,
            "response_format": "mp3",
            "speed": 0.98,
        }
    ).encode("utf-8")
    req = urlrequest.Request(
        "https://api.openai.com/v1/audio/speech",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen_with_rate_limit_retry(req, timeout=60) as resp:
            audio = resp.read()
        if not audio:
            return {"audio": None, "error": "tts_empty"}
        return {"audio": audio, "mime": "audio/mpeg", "model": model, "voice": voice, "lang": lang[:2]}
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        logger.warning("OpenAI TTS HTTP %s: %s", exc.code, detail)
        parsed = parse_openai_http_error(detail)
        return {"audio": None, "error": parsed.get("error", "tts_http_error"), "hint": parsed.get("hint")}
    except Exception as exc:
        return {"audio": None, "error": "tts_failed", "hint": str(exc)[:300]}
