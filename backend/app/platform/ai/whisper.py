"""OpenAI / Azure OpenAI Whisper transcription for voice input."""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from .openai_errors import parse_openai_http_error, urlopen_with_rate_limit_retry

logger = logging.getLogger("baupass.ai.whisper")


@dataclass(frozen=True)
class WhisperProvider:
    provider: str
    url: str
    headers: dict[str, str]
    model: str
    include_model_field: bool


def _looks_like_openai_key(value: str) -> bool:
    v = (value or "").strip()
    return v.startswith("sk-") or v.startswith("sk_proj")


def _prefer_openai_direct() -> bool:
    """When both Azure and OpenAI keys exist, default to direct OpenAI (user billing)."""
    prefer = (os.getenv("BAUPASS_AI_PREFER") or os.getenv("BAUPASS_WHISPER_PREFER") or "openai").strip().lower()
    if prefer in {"azure", "foundry"}:
        return False
    return bool((os.getenv("OPENAI_API_KEY") or "").strip())


def list_whisper_providers() -> list[WhisperProvider]:
    """OpenAI first when configured (better multilingual/Arabic), then Azure."""
    providers: list[WhisperProvider] = []
    azure_list: list[WhisperProvider] = []
    openai_list: list[WhisperProvider] = []

    azure_key = (os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
    if azure_key:
        endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip().rstrip("/")
        if endpoint:
            deployment = (
                (os.getenv("AZURE_OPENAI_WHISPER_DEPLOYMENT") or "").strip()
                or (os.getenv("BAUPASS_WHISPER_DEPLOYMENT") or "").strip()
                or "whisper"
            )
            if _looks_like_openai_key(deployment):
                deployment = "whisper"
            api_version = (
                (os.getenv("AZURE_OPENAI_WHISPER_API_VERSION") or "").strip()
                or (os.getenv("AZURE_OPENAI_API_VERSION") or "").strip()
                or "2024-02-01"
            )
            azure_list.append(
                WhisperProvider(
                    provider="azure",
                    url=f"{endpoint}/openai/deployments/{deployment}/audio/transcriptions?api-version={api_version}",
                    headers={"api-key": azure_key},
                    model=deployment,
                    include_model_field=False,
                )
            )
        else:
            logger.warning("AZURE_OPENAI_API_KEY set but AZURE_OPENAI_ENDPOINT missing — Whisper Azure skipped")

    openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if openai_key:
        model = (os.getenv("BAUPASS_WHISPER_MODEL") or "whisper-1").strip()
        openai_list.append(
            WhisperProvider(
                provider="openai",
                url="https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {openai_key}"},
                model=model,
                include_model_field=True,
            )
        )

    if _prefer_openai_direct():
        providers.extend(openai_list)
        providers.extend(azure_list)
    else:
        providers.extend(azure_list)
        providers.extend(openai_list)
    return providers


def is_whisper_configured() -> bool:
    return bool(list_whisper_providers())


def whisper_config_status() -> dict[str, Any]:
    providers = list_whisper_providers()
    if not providers:
        return {"configured": False, "provider": None}
    primary = providers[0]
    return {"configured": True, "provider": primary.provider, "model": primary.model}


def _transcribe_with_provider(
    audio_bytes: bytes,
    *,
    filename: str,
    mime: str,
    language: str | None,
    provider: WhisperProvider,
) -> dict[str, Any]:
    lang = (language or os.getenv("BAUPASS_WHISPER_LANG") or "").strip()[:2]
    auto_lang = not lang or lang.lower() in {"auto", "mul", "*", "xx"}

    boundary = f"----Baupass{uuid.uuid4().hex}"
    crlf = b"\r\n"
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(value.encode())

    if provider.include_model_field:
        add_field("model", provider.model)
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
    headers = {**provider.headers, "Content-Type": f"multipart/form-data; boundary={boundary}"}
    req = urlrequest.Request(provider.url, data=body, headers=headers, method="POST")
    try:
        with urlopen_with_rate_limit_retry(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (data.get("text") or "").strip()
        if not text or len(text) < 2:
            return {"text": None, "error": "no_speech_detected"}
        if not any("\u0600" <= ch <= "\u06FF" for ch in text) and all(
            ch in ".,;:!?…-–—'\"` " for ch in text
        ):
            return {"text": None, "error": "no_speech_detected"}
        return {"text": text, "model": provider.model, "provider": provider.provider}
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        logger.warning("Whisper HTTP %s (%s): %s", exc.code, provider.provider, detail)
        parsed = parse_openai_http_error(detail)
        if parsed.get("error") == "openai_http_error":
            parsed["error"] = "whisper_http_error"
        parsed["provider"] = provider.provider
        return {"text": None, **parsed}
    except Exception as exc:
        return {
            "text": None,
            "error": "whisper_failed",
            "hint": str(exc)[:300],
            "provider": provider.provider,
        }



def transcribe_audio_bytes(
    audio_bytes: bytes,
    *,
    filename: str = "audio.webm",
    mime: str = "audio/webm",
    language: str | None = None,
) -> dict[str, Any]:
    providers = list_whisper_providers()
    if not providers:
        return {"text": None, "error": "openai_not_configured"}

    if not audio_bytes or len(audio_bytes) < 500:
        return {"text": None, "error": "audio_too_short"}

    last_result: dict[str, Any] | None = None
    for i, provider in enumerate(providers):
        result = _transcribe_with_provider(
            audio_bytes,
            filename=filename,
            mime=mime,
            language=language,
            provider=provider,
        )
        if result.get("text"):
            return result
        last_result = result
        if i >= len(providers) - 1:
            return result

    return last_result or {"text": None, "error": "openai_not_configured"}
