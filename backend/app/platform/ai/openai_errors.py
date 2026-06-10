"""Parse OpenAI / Azure OpenAI HTTP error bodies into stable BauPass codes."""
from __future__ import annotations

import json
from typing import Any


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
    if oai_code == "rate_limit_exceeded":
        return {"error": "openai_rate_limit", "hint": "OpenAI rate limit — try again shortly."}
    if oai_code == "model_not_found" or "model_not_found" in text:
        return {
            "error": "openai_model_not_found",
            "hint": "Model not found — set BAUPASS_AI_MODEL to a model your API key can use (e.g. gpt-4o-mini).",
        }
    if message:
        return {"error": "openai_http_error", "hint": message[:400]}
    return {"error": "openai_http_error", "hint": text[:400]}
