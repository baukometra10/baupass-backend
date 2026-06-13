"""Text-to-speech — OpenAI default with Ghizlane / Ramona / Vanessa personas per language."""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from typing import Any, Generator

from urllib import error as urlerror
from urllib import request as urlrequest

from .openai_errors import parse_openai_http_error, urlopen_with_rate_limit_retry

logger = logging.getLogger("baupass.ai.tts")

# Persona labels (from ElevenLabs previews) — OpenAI voices tuned to match each character.
_VOICE_PERSONAS = {
    "ar": {
        "name": "Ghizlane",
        "openai_voice": "marin",
        "instructions": (
            "Smooth, distinctive, calm female voice — natural Modern Standard Arabic (فصحى). "
            "Warm, fluent, human-like intonation like a premium assistant. "
            "Clear articulation, gentle pace, never robotic."
        ),
    },
    "de": {
        "name": "Ramona",
        "openai_voice": "coral",
        "instructions": (
            "Professional and calm female voice — natural Hochdeutsch. "
            "Confident, warm, clear business tone like a trusted colleague. "
            "Steady pace, never robotic or overly cheerful."
        ),
    },
    "en": {
        "name": "Vanessa",
        "openai_voice": "shimmer",
        "instructions": (
            "Friendly, youthful, upbeat female voice — natural conversational English. "
            "Warm and approachable like a helpful guide. Clear, lively, never robotic."
        ),
    },
}

_ELEVENLABS_VOICES = {
    "ar": "u0TsaWvt0v8migutHM3M",
    "de": "6CS8keYmkwxkspesdyA7",
    "en": "8DzKSPdgEQPaK5vKG0Rs",
}

_MIME_BY_FORMAT = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "opus": "audio/opus",
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


def _persona(lang: str) -> dict[str, str]:
    lang = (lang or "de")[:2]
    return _VOICE_PERSONAS.get(lang) or _VOICE_PERSONAS["en"]


def _openai_api_key() -> str:
    return (os.getenv("OPENAI_API_KEY") or "").strip()


def _elevenlabs_api_key() -> str:
    return (os.getenv("ELEVENLABS_API_KEY") or os.getenv("BAUPASS_ELEVENLABS_API_KEY") or "").strip()


def _resolve_tts_provider() -> str:
    explicit = (os.getenv("BAUPASS_TTS_PROVIDER") or "openai").strip().lower()
    if explicit == "elevenlabs" and _elevenlabs_api_key():
        return "elevenlabs"
    return "openai"


def _resolve_openai_config(lang: str) -> dict[str, Any]:
    lang = (lang or "de")[:2]
    persona = _persona(lang)
    voice_env = {
        "ar": "BAUPASS_TTS_VOICE_AR",
        "de": "BAUPASS_TTS_VOICE_DE",
        "en": "BAUPASS_TTS_VOICE_EN",
    }.get(lang, "BAUPASS_TTS_VOICE_EN")
    instructions_env = {
        "ar": "BAUPASS_TTS_INSTRUCTIONS_AR",
        "de": "BAUPASS_TTS_INSTRUCTIONS_DE",
        "en": "BAUPASS_TTS_INSTRUCTIONS_EN",
    }.get(lang, "BAUPASS_TTS_INSTRUCTIONS_EN")
    model = (
        os.getenv(f"BAUPASS_TTS_MODEL_{lang.upper()}")
        or os.getenv("BAUPASS_TTS_MODEL")
        or "gpt-4o-mini-tts"
    ).strip()
    return {
        "model": model,
        "voice": (os.getenv(voice_env) or persona["openai_voice"]).strip(),
        "voice_name": persona["name"],
        "instructions": (os.getenv(instructions_env) or persona["instructions"]).strip(),
        "response_format": "mp3",
    }


def _resolve_elevenlabs_config(lang: str) -> dict[str, Any]:
    lang = (lang or "de")[:2]
    persona = _persona(lang)
    return {
        "voice_id": _ELEVENLABS_VOICES.get(lang) or _ELEVENLABS_VOICES["en"],
        "voice_name": persona["name"],
        "model_id": (os.getenv("BAUPASS_ELEVENLABS_MODEL") or "eleven_multilingual_v2").strip(),
        "output_format": (os.getenv("BAUPASS_ELEVENLABS_FORMAT") or "mp3_44100_128").strip(),
    }


def _build_openai_payload(cleaned: str, config: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": config["model"],
        "input": cleaned,
        "voice": config["voice"],
        "response_format": config.get("response_format") or "mp3",
    }
    instructions = config.get("instructions")
    if instructions and str(config["model"]).startswith("gpt-4o-mini-tts"):
        payload["instructions"] = instructions
    return payload


def _openai_tts_request(cleaned: str, config: dict[str, Any], *, timeout: int = 25, fast: bool = False):
    key = _openai_api_key()
    if not key:
        raise ValueError("openai_not_configured")
    payload = json.dumps(_build_openai_payload(cleaned, config)).encode("utf-8")
    req = urlrequest.Request(
        "https://api.openai.com/v1/audio/speech",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    if fast:
        return urlrequest.urlopen(req, timeout=timeout)
    return urlopen_with_rate_limit_retry(req, timeout=timeout, max_attempts=2)


def _elevenlabs_tts_request(cleaned: str, config: dict[str, Any], *, timeout: int = 25, fast: bool = False):
    key = _elevenlabs_api_key()
    if not key:
        raise ValueError("elevenlabs_not_configured")
    voice_id = str(config["voice_id"])
    query = f"output_format={config.get('output_format') or 'mp3_44100_128'}"
    body = {
        "text": cleaned,
        "model_id": config.get("model_id") or "eleven_multilingual_v2",
    }
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


def _synthesize_openai_bytes(cleaned: str, *, lang: str, fast: bool) -> dict[str, Any]:
    if not _openai_api_key():
        return {
            "audio": None,
            "error": "openai_not_configured",
            "hint": "Set OPENAI_API_KEY on the server.",
            "provider": "openai",
        }
    config = _resolve_openai_config(lang)
    fmt = str(config.get("response_format") or "mp3")
    try:
        with _openai_tts_request(cleaned, config, timeout=22 if fast else 35, fast=fast) as resp:
            audio = resp.read()
        if not audio:
            return {"audio": None, "error": "tts_empty", "provider": "openai"}
        return {
            "audio": audio,
            "mime": _MIME_BY_FORMAT.get(fmt, "audio/mpeg"),
            "model": config["model"],
            "voice": config["voice"],
            "voiceName": config["voice_name"],
            "lang": lang[:2],
            "format": fmt,
            "provider": "openai",
        }
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        logger.warning("OpenAI TTS HTTP %s: %s", exc.code, detail)
        parsed = parse_openai_http_error(detail)
        return {
            "audio": None,
            "error": parsed.get("error", "tts_http_error"),
            "hint": parsed.get("hint"),
            "provider": "openai",
        }
    except Exception as exc:
        return {"audio": None, "error": "tts_failed", "hint": str(exc)[:300], "provider": "openai"}


def _synthesize_elevenlabs_bytes(cleaned: str, *, lang: str, fast: bool) -> dict[str, Any]:
    if not _elevenlabs_api_key():
        return {
            "audio": None,
            "error": "elevenlabs_not_configured",
            "provider": "elevenlabs",
        }
    config = _resolve_elevenlabs_config(lang)
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

    provider = _resolve_tts_provider()
    if provider == "elevenlabs":
        result = _synthesize_elevenlabs_bytes(cleaned, lang=lang, fast=fast)
        if result.get("audio"):
            return result
        if _openai_api_key():
            logger.warning("ElevenLabs failed (%s), using OpenAI", result.get("error"))
            return _synthesize_openai_bytes(cleaned, lang=lang, fast=fast)
        return result

    return _synthesize_openai_bytes(cleaned, lang=lang, fast=fast)


def tts_config_status() -> dict[str, Any]:
    provider = _resolve_tts_provider()
    voices = {
        lang: {
            "name": persona["name"],
            "openaiVoice": persona["openai_voice"],
            "elevenLabsId": _ELEVENLABS_VOICES.get(lang),
        }
        for lang, persona in _VOICE_PERSONAS.items()
    }
    openai_ok = bool(_openai_api_key())
    eleven_ok = bool(_elevenlabs_api_key())
    configured = openai_ok if provider == "openai" else eleven_ok
    hint = None
    if not configured:
        hint = (
            "Set OPENAI_API_KEY (default) or ELEVENLABS_API_KEY with BAUPASS_TTS_PROVIDER=elevenlabs."
        )
    return {
        "provider": provider,
        "configured": configured,
        "openaiConfigured": openai_ok,
        "elevenLabsConfigured": eleven_ok,
        "model": _resolve_openai_config("de")["model"],
        "voices": voices,
        "hint": hint,
    }


def synthesize_speech_stream(
    text: str,
    *,
    lang: str = "de",
    fast: bool = True,
) -> Generator[bytes, None, None]:
    cleaned = prepare_tts_text(text, lang=lang, fast=fast)
    if not cleaned or len(cleaned) < 2:
        return
    result = synthesize_speech_bytes(text, lang=lang, fast=fast)
    audio = result.get("audio")
    if audio:
        yield audio
