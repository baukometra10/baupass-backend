"""OpenAI text-to-speech for AI voice replies."""
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

_AR_TTS_INSTRUCTIONS = (
    "Speak like ChatGPT voice: clear conversational Modern Standard Arabic (الفصحى). "
    "Crisp pronunciation, natural warm tone, steady pace — every word easy to understand."
)

_MIME_BY_FORMAT = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "pcm": "audio/pcm",
}


def prepare_tts_text(text: str, *, lang: str, fast: bool = False) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    lang = (lang or "de")[:2]
    if lang == "ar":
        cleaned = unicodedata.normalize("NFKC", cleaned)
        cleaned = cleaned.replace("\u0640", "")
        cleaned = re.sub(r"[\u200c\u200d\u200e\u200f\ufeff]", "", cleaned)
        cleaned = re.sub(r"[*_#>`|\[\](){}]", "", cleaned)
        cleaned = re.sub(r"([،؛:])(?=\S)", r"\1 ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
    max_len = 140 if (lang == "ar" and fast) else (220 if fast else 4096)
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[:max_len]
    for sep in ("؟", "!", "?", ".", "…", "،"):
        idx = cut.rfind(sep)
        if idx >= max(30, max_len // 4):
            return cut[: idx + 1].strip()
    return cut.rstrip() + "…"


def _resolve_tts_config(lang: str, *, fast: bool = False) -> dict[str, Any]:
    lang = (lang or "de")[:2]
    if lang == "ar":
        model = (os.getenv("BAUPASS_TTS_MODEL_AR") or "gpt-4o-mini-tts").strip()
        voice = (os.getenv("BAUPASS_TTS_VOICE_AR") or "coral").strip()
        return {
            "model": model,
            "voice": voice,
            "instructions": (os.getenv("BAUPASS_TTS_INSTRUCTIONS_AR") or _AR_TTS_INSTRUCTIONS).strip(),
            "response_format": "mp3",
            "speed": None,
        }
    model = (os.getenv("BAUPASS_TTS_MODEL") or "tts-1").strip()
    voice = (os.getenv("BAUPASS_TTS_VOICE") or "nova").strip()
    return {
        "model": model,
        "voice": voice,
        "instructions": None,
        "response_format": "mp3",
        "speed": 0.98,
    }


def _build_tts_payload(cleaned: str, config: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": config["model"],
        "input": cleaned,
        "voice": config["voice"],
        "response_format": config.get("response_format") or "mp3",
    }
    instructions = config.get("instructions")
    if instructions and str(config["model"]).startswith("gpt-4o-mini-tts"):
        payload["instructions"] = instructions
    elif config.get("speed") is not None:
        payload["speed"] = config["speed"]
    return payload


def _openai_tts_request(cleaned: str, config: dict[str, Any], *, timeout: int = 20, fast: bool = False):
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise ValueError("openai_not_configured")
    payload = json.dumps(_build_tts_payload(cleaned, config)).encode("utf-8")
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


def synthesize_speech_bytes(
    text: str,
    *,
    lang: str = "de",
    fast: bool = False,
) -> dict[str, Any]:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return {"audio": None, "error": "openai_not_configured"}
    cleaned = prepare_tts_text(text, lang=lang, fast=fast)
    if not cleaned or len(cleaned) < 2:
        return {"audio": None, "error": "text_too_short"}

    config = _resolve_tts_config(lang, fast=fast)
    fmt = str(config.get("response_format") or "mp3")
    try:
        with _openai_tts_request(cleaned, config, timeout=18 if fast else 30, fast=fast) as resp:
            audio = resp.read()
        if not audio:
            return {"audio": None, "error": "tts_empty"}
        return {
            "audio": audio,
            "mime": _MIME_BY_FORMAT.get(fmt, "audio/mpeg"),
            "model": config["model"],
            "voice": config["voice"],
            "lang": lang[:2],
            "format": fmt,
        }
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        logger.warning("OpenAI TTS HTTP %s: %s", exc.code, detail)
        if config["model"] != "tts-1" and lang[:2] == "ar":
            fallback = {**config, "model": "tts-1", "instructions": None, "response_format": "mp3", "speed": 0.96}
            try:
                with _openai_tts_request(cleaned, fallback, timeout=15, fast=True) as resp:
                    audio = resp.read()
                if audio:
                    return {
                        "audio": audio,
                        "mime": "audio/mpeg",
                        "model": "tts-1",
                        "voice": config["voice"],
                        "lang": lang[:2],
                        "format": "mp3",
                    }
            except Exception:
                pass
        parsed = parse_openai_http_error(detail)
        return {"audio": None, "error": parsed.get("error", "tts_http_error"), "hint": parsed.get("hint")}
    except Exception as exc:
        return {"audio": None, "error": "tts_failed", "hint": str(exc)[:300]}


def synthesize_speech_stream(
    text: str,
    *,
    lang: str = "de",
    fast: bool = True,
) -> Generator[bytes, None, None]:
    """Stream audio bytes from OpenAI TTS."""
    cleaned = prepare_tts_text(text, lang=lang, fast=fast)
    if not cleaned or len(cleaned) < 2:
        return
    config = _resolve_tts_config(lang, fast=True)
    try:
        resp = _openai_tts_request(cleaned, config, timeout=18, fast=True)
    except Exception as exc:
        logger.warning("TTS stream open failed: %s", exc)
        return
    try:
        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            yield chunk
    finally:
        try:
            resp.close()
        except Exception:
            pass
