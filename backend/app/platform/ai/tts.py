"""ElevenLabs text-to-speech — fixed voices per language (Ghizlane / Ramona / Vanessa)."""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from typing import Any, Generator

from urllib import error as urlerror
from urllib import request as urlrequest

from .openai_errors import urlopen_with_rate_limit_retry

logger = logging.getLogger("baupass.ai.tts")

# Only the three ElevenLabs voices chosen by the platform owner.
_ELEVENLABS_VOICES = {
    "ar": "u0TsaWvt0v8migutHM3M",  # Ghizlane — smooth, distinctive and calm
    "de": "6CS8keYmkwxkspesdyA7",  # Ramona — professional and calm
    "en": "8DzKSPdgEQPaK5vKG0Rs",  # Vanessa — beach girl
}

_ELEVENLABS_VOICE_NAMES = {
    "ar": "Ghizlane",
    "de": "Ramona",
    "en": "Vanessa",
}

_ELEVENLABS_LANG = {
    "ar": "ar",
    "de": "de",
    "en": "en",
}


def prepare_tts_text(text: str, *, lang: str, fast: bool = False) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    lang = (lang or "de")[:2]
    cleaned = re.sub(r"[*_#>`|\[\](){}]", "", cleaned)
    if lang == "ar":
        cleaned = unicodedata.normalize("NFKC", cleaned)
        cleaned = cleaned.replace("\u0640", "")
        cleaned = re.sub(r"[\u200c\u200d\u200e\u200f\ufeff]", "", cleaned)
        cleaned = re.sub(r"([،؛:])(?=\S)", r"\1 ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    max_len = 280 if fast else 4096
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[:max_len]
    for sep in ("؟", "!", "?", ".", "…", "،"):
        idx = cut.rfind(sep)
        if idx >= max(30, max_len // 4):
            return cut[: idx + 1].strip()
    return cut.rstrip() + "…"


def _elevenlabs_api_key() -> str:
    return (os.getenv("ELEVENLABS_API_KEY") or os.getenv("BAUPASS_ELEVENLABS_API_KEY") or "").strip()


def _resolve_elevenlabs_config(lang: str, *, fast: bool = False) -> dict[str, Any]:
    lang = (lang or "de")[:2]
    voice_id = _ELEVENLABS_VOICES.get(lang) or _ELEVENLABS_VOICES["en"]
    return {
        "voice_id": voice_id,
        "voice_name": _ELEVENLABS_VOICE_NAMES.get(lang) or _ELEVENLABS_VOICE_NAMES["en"],
        "model_id": (os.getenv("BAUPASS_ELEVENLABS_MODEL") or "eleven_multilingual_v2").strip(),
        "language_code": _ELEVENLABS_LANG.get(lang, "en"),
        "output_format": (os.getenv("BAUPASS_ELEVENLABS_FORMAT") or "mp3_44100_128").strip(),
        "optimize_streaming_latency": 3 if fast else None,
    }


def _elevenlabs_tts_request(
    cleaned: str,
    config: dict[str, Any],
    *,
    timeout: int = 25,
    fast: bool = False,
):
    key = _elevenlabs_api_key()
    if not key:
        raise ValueError("elevenlabs_not_configured")
    voice_id = str(config["voice_id"])
    query = f"output_format={config.get('output_format') or 'mp3_44100_128'}"
    latency = config.get("optimize_streaming_latency")
    if fast and latency is not None:
        query += f"&optimize_streaming_latency={latency}"
    body = {
        "text": cleaned,
        "model_id": config.get("model_id") or "eleven_multilingual_v2",
    }
    # Do not force language_code — multilingual v2 auto-detects; forced codes can 422.
    payload = json.dumps(body).encode("utf-8")
    req = urlrequest.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?{query}",
        data=payload,
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    if fast:
        return urlrequest.urlopen(req, timeout=timeout)
    return urlopen_with_rate_limit_retry(req, timeout=timeout, max_attempts=2)


def _synthesize_elevenlabs_bytes(
    cleaned: str,
    *,
    lang: str,
    fast: bool,
) -> dict[str, Any]:
    if not _elevenlabs_api_key():
        return {
            "audio": None,
            "error": "elevenlabs_not_configured",
            "hint": "Set ELEVENLABS_API_KEY on the server.",
            "provider": "elevenlabs",
        }
    config = _resolve_elevenlabs_config(lang, fast=fast)
    try:
        with _elevenlabs_tts_request(cleaned, config, timeout=22 if fast else 35, fast=fast) as resp:
            audio = resp.read()
        if not audio:
            return {"audio": None, "error": "tts_empty", "provider": "elevenlabs"}
        return {
            "audio": audio,
            "mime": "audio/mpeg",
            "model": config["model_id"],
            "voice": config["voice_id"],
            "voiceName": config["voice_name"],
            "lang": lang[:2],
            "format": "mp3",
            "provider": "elevenlabs",
        }
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        logger.warning("ElevenLabs TTS HTTP %s: %s", exc.code, detail)
        return {
            "audio": None,
            "error": "elevenlabs_http_error",
            "hint": detail[:300],
            "provider": "elevenlabs",
        }
    except Exception as exc:
        return {"audio": None, "error": "tts_failed", "hint": str(exc)[:300], "provider": "elevenlabs"}


def synthesize_speech_bytes(
    text: str,
    *,
    lang: str = "de",
    fast: bool = False,
) -> dict[str, Any]:
    cleaned = prepare_tts_text(text, lang=lang, fast=fast)
    if not cleaned or len(cleaned) < 2:
        return {"audio": None, "error": "text_too_short"}
    return _synthesize_elevenlabs_bytes(cleaned, lang=lang, fast=fast)


def tts_config_status() -> dict[str, Any]:
    key_ok = bool(_elevenlabs_api_key())
    voices = {
        lang: {
            "id": voice_id,
            "name": _ELEVENLABS_VOICE_NAMES.get(lang) or lang,
        }
        for lang, voice_id in _ELEVENLABS_VOICES.items()
    }
    hint = None
    if not key_ok:
        hint = (
            "Set ELEVENLABS_API_KEY (or BAUPASS_ELEVENLABS_API_KEY) on the server, "
            "then redeploy Railway."
        )
    return {
        "provider": "elevenlabs",
        "configured": key_ok,
        "envVars": ["ELEVENLABS_API_KEY", "BAUPASS_ELEVENLABS_API_KEY"],
        "model": (os.getenv("BAUPASS_ELEVENLABS_MODEL") or "eleven_multilingual_v2").strip(),
        "voices": voices,
        "hint": hint,
    }


def synthesize_speech_stream(
    text: str,
    *,
    lang: str = "de",
    fast: bool = True,
) -> Generator[bytes, None, None]:
    """Return ElevenLabs audio (single chunk — no alternate provider)."""
    cleaned = prepare_tts_text(text, lang=lang, fast=fast)
    if not cleaned or len(cleaned) < 2:
        return
    result = _synthesize_elevenlabs_bytes(cleaned, lang=lang, fast=fast)
    audio = result.get("audio")
    if audio:
        yield audio
