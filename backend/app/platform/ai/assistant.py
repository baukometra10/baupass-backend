"""
AI assistant — OpenAI or Azure OpenAI when keys are configured.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

logger = logging.getLogger("baupass.ai")


def is_ai_configured() -> bool:
    return bool(
        os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    )


def _chat_completion(messages: list[dict[str, str]]) -> dict[str, Any]:
    azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("BAUPASS_AI_MODEL", "gpt-4o-mini")

    if azure_key:
        endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip().rstrip("/")
        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT is required when using AZURE_OPENAI_API_KEY")
        deployment = (os.getenv("AZURE_OPENAI_DEPLOYMENT") or model).strip()
        api_version = (os.getenv("AZURE_OPENAI_API_VERSION") or "2024-02-15-preview").strip()
        url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        headers = {"api-key": azure_key, "Content-Type": "application/json"}
        payload_model = deployment
    elif openai_key:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
        payload_model = model
    else:
        raise ValueError("No OpenAI API key configured")

    payload = json.dumps(
        {
            "model": payload_model,
            "messages": messages,
            "temperature": 0.2,
        }
    ).encode("utf-8")
    req = urlrequest.Request(url, data=payload, headers=headers, method="POST")
    with urlrequest.urlopen(req, timeout=90) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body


def natural_language_query(
    company_id: str,
    question: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not is_ai_configured():
        return {
            "answer": None,
            "configured": False,
            "hint": "Set OPENAI_API_KEY or AZURE_OPENAI_API_KEY (+ AZURE_OPENAI_ENDPOINT) on the server.",
        }

    system = (
        "You are BauPass workforce assistant. Answer briefly in the user's language. "
        "Use only the provided JSON context; do not invent employee data."
    )
    user_content = json.dumps(
        {"question": question, "context": context or {}, "company_id": company_id},
        ensure_ascii=False,
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    model = os.getenv("BAUPASS_AI_MODEL", "gpt-4o-mini")

    try:
        body = _chat_completion(messages)
        answer = body["choices"][0]["message"]["content"]
        return {"answer": answer, "configured": True, "model": model}
    except urlerror.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            detail = str(exc)
        logger.warning("OpenAI HTTP error %s: %s", exc.code, detail)
        return {
            "answer": None,
            "configured": True,
            "error": "openai_http_error",
            "hint": f"KI-Anfrage fehlgeschlagen (HTTP {exc.code}). Prüfe API-Key, Modell und Guthaben. {detail}",
        }
    except Exception as exc:
        logger.exception("AI query failed for company %s", company_id)
        return {
            "answer": None,
            "configured": True,
            "error": "ai_request_failed",
            "hint": f"KI-Anfrage fehlgeschlagen: {exc}",
        }
