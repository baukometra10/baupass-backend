"""
AI assistant — OpenAI or Azure OpenAI when keys are configured.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

logger = logging.getLogger("baupass.ai")

DEFAULT_AI_MODEL = "gpt-4o-mini"
_SK_TOKEN_RE = re.compile(r"sk-[A-Za-z0-9_-]{8,}")


def _looks_like_openai_key(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    return v.startswith("sk-") or v.startswith("sk_proj")


def _sanitize_error_detail(detail: str) -> str:
    return _SK_TOKEN_RE.sub("sk-***", detail or "")


def resolve_ai_model() -> tuple[str, str | None]:
    """Return (model_or_deployment_name, config_warning_or_none)."""
    raw_model = (os.getenv("BAUPASS_AI_MODEL") or "").strip()
    azure_deployment = (os.getenv("AZURE_OPENAI_DEPLOYMENT") or "").strip()

    if _looks_like_openai_key(raw_model):
        logger.warning("BAUPASS_AI_MODEL looks like an API key; using %s", DEFAULT_AI_MODEL)
        return DEFAULT_AI_MODEL, (
            "BAUPASS_AI_MODEL enthält den API-Key statt eines Modellnamens. "
            "Key nur in OPENAI_API_KEY setzen; Modell z. B. gpt-4o-mini (optional)."
        )
    if azure_deployment and _looks_like_openai_key(azure_deployment):
        logger.warning("AZURE_OPENAI_DEPLOYMENT looks like an API key; using %s", DEFAULT_AI_MODEL)
        return DEFAULT_AI_MODEL, (
            "AZURE_OPENAI_DEPLOYMENT enthält den API-Key. "
            "Nur den Deployment-Namen setzen (z. B. gpt-4o-mini)."
        )
    return (raw_model or DEFAULT_AI_MODEL), None


def ai_config_status() -> dict[str, Any]:
    model, warning = resolve_ai_model()
    azure = bool((os.getenv("AZURE_OPENAI_API_KEY") or "").strip())
    openai = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    return {
        "configured": openai or azure,
        "provider": "azure" if azure else ("openai" if openai else None),
        "model": model,
        "configWarning": warning,
    }


def is_ai_configured() -> bool:
    return bool(
        os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    )


def _chat_completion(messages: list[dict[str, str]]) -> dict[str, Any]:
    azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    model, _warn = resolve_ai_model()

    if azure_key:
        endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip().rstrip("/")
        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT is required when using AZURE_OPENAI_API_KEY")
        deployment = (os.getenv("AZURE_OPENAI_DEPLOYMENT") or "").strip()
        if _looks_like_openai_key(deployment):
            deployment = model
        elif not deployment:
            deployment = model
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
    model, config_warning = resolve_ai_model()

    try:
        body = _chat_completion(messages)
        answer = body["choices"][0]["message"]["content"]
        out: dict[str, Any] = {"answer": answer, "configured": True, "model": model}
        if config_warning:
            out["configWarning"] = config_warning
        return out
    except urlerror.HTTPError as exc:
        detail = ""
        try:
            detail = _sanitize_error_detail(exc.read().decode("utf-8", errors="replace")[:800])
        except Exception:
            detail = _sanitize_error_detail(str(exc))
        logger.warning("OpenAI HTTP error %s: %s", exc.code, detail)
        hint = f"KI-Anfrage fehlgeschlagen (HTTP {exc.code}). Prüfe API-Key, Modell und Guthaben."
        if config_warning:
            hint = f"{config_warning} {hint}"
        elif "model_not_found" in detail or _looks_like_openai_key(detail):
            hint = (
                "Modell-Variable falsch: API-Key gehört in OPENAI_API_KEY, "
                "nicht in BAUPASS_AI_MODEL. Modell z. B. gpt-4o-mini. "
                + hint
            )
        if detail:
            hint = f"{hint} {detail}"
        return {
            "answer": None,
            "configured": True,
            "error": "openai_http_error",
            "hint": hint,
        }
    except Exception as exc:
        logger.exception("AI query failed for company %s", company_id)
        return {
            "answer": None,
            "configured": True,
            "error": "ai_request_failed",
            "hint": f"KI-Anfrage fehlgeschlagen: {exc}",
        }
