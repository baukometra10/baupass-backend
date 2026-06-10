"""Parse OpenAI / Azure OpenAI HTTP error bodies into stable BauPass codes."""
from __future__ import annotations

import json
import time
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

OPENAI_429_MAX_ATTEMPTS = 3
OPENAI_429_BACKOFF_SECONDS = (2.0, 6.0, 15.0)


class OpenAiApiError(Exception):
    def __init__(self, code: str, hint: str):
        self.code = code
        self.hint = hint
        super().__init__(hint)


def parse_openai_http_error(detail: str) -> dict[str, Any]:
    text = (detail or "").strip()
    if not text:
        return {"error": "openai_http_error", "hint": "OpenAI request failed."}

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
            "hint": (
                "OpenAI API quota exceeded. ChatGPT Plus is not API billing — "
                "add credits at platform.openai.com/settings/billing and use the same key in OPENAI_API_KEY."
            ),
        }
    if oai_code in {"invalid_api_key", "authentication_error"} or "invalid api key" in message.lower():
        return {"error": "openai_auth_error", "hint": "Invalid OPENAI_API_KEY on the server."}
    if oai_code == "rate_limit_exceeded" or _looks_like_openai_rate_limit(message, text):
        hint = message[:400] if message else "OpenAI rate limit — try again shortly."
        return {"error": "openai_rate_limit", "hint": hint}
    if oai_code == "model_not_found" or "model_not_found" in text:
        return {
            "error": "openai_model_not_found",
            "hint": "Model not found — set BAUPASS_AI_MODEL to a model your API key can use (e.g. gpt-4o-mini).",
        }
    if message:
        return {"error": "openai_http_error", "hint": message[:400]}
    return {"error": "openai_http_error", "hint": text[:400]}


def _looks_like_openai_rate_limit(message: str, raw: str) -> bool:
    blob = f"{message} {raw}".lower()
    if "rate limit" not in blob and "too many requests" not in blob:
        return False
    return any(
        token in blob
        for token in (
            "tpm",
            "rpm",
            "tokens per min",
            "requests per min",
            "gpt-",
            "openai",
        )
    )


def urlopen_with_rate_limit_retry(req: urlrequest.Request, *, timeout: int = 90, max_attempts: int | None = None):
    """Perform HTTP request with exponential backoff on OpenAI HTTP 429."""
    attempts = max_attempts if max_attempts is not None else OPENAI_429_MAX_ATTEMPTS
    last_exc: urlerror.HTTPError | None = None
    for attempt in range(max(1, attempts)):
        try:
            return urlrequest.urlopen(req, timeout=timeout)
        except urlerror.HTTPError as exc:
            last_exc = exc
            if exc.code == 429 and attempt < attempts - 1:
                delays = OPENAI_429_BACKOFF_SECONDS
                time.sleep(delays[attempt] if attempt < len(delays) else delays[-1])
                continue
            raise
    if last_exc:
        raise last_exc
    raise urlerror.URLError("OpenAI request failed")
