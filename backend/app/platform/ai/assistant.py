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
    from .agents import list_agents

    model, warning = resolve_ai_model()
    azure = bool((os.getenv("AZURE_OPENAI_API_KEY") or "").strip())
    openai = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    tools_on = os.getenv("BAUPASS_AI_TOOLS", "1").strip().lower() not in {"0", "false", "no"}
    return {
        "configured": openai or azure,
        "provider": "azure" if azure else ("openai" if openai else None),
        "model": model,
        "configWarning": warning,
        "agentsEnabled": bool(openai or azure),
        "toolCalling": tools_on,
        "agents": list_agents("de"),
        "features": [
            "chat",
            "briefing",
            "prompts",
            "agents",
            "sessions",
            "insights",
            "deep_analysis",
            "streaming",
            "actions",
            "rag",
            "briefing_email",
        ],
    }


def is_ai_configured() -> bool:
    return bool(
        os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    )


def _chat_completion(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict = "auto",
) -> dict[str, Any]:
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

    body: dict[str, Any] = {
        "model": payload_model,
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice
    payload = json.dumps(body).encode("utf-8")
    req = urlrequest.Request(url, data=payload, headers=headers, method="POST")
    with urlrequest.urlopen(req, timeout=90) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body


def _openai_request_config() -> tuple[str, dict[str, str], str]:
    """Return (url, headers, model) for OpenAI-compatible chat API."""
    azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    model, _ = resolve_ai_model()
    if azure_key:
        endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip().rstrip("/")
        deployment = (os.getenv("AZURE_OPENAI_DEPLOYMENT") or "").strip() or model
        if _looks_like_openai_key(deployment):
            deployment = model
        api_version = (os.getenv("AZURE_OPENAI_API_VERSION") or "2024-02-15-preview").strip()
        url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        return url, {"api-key": azure_key, "Content-Type": "application/json"}, deployment
    if openai_key:
        return (
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
            model,
        )
    raise ValueError("No OpenAI API key configured")


def _openai_stream_request(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
):
    """Yield text deltas from streaming chat completion."""
    url, headers, payload_model = _openai_request_config()
    body: dict[str, Any] = {
        "model": payload_model,
        "messages": messages,
        "temperature": 0.2,
        "stream": True,
    }
    if tools:
        body["tools"] = tools
    payload = json.dumps(body).encode("utf-8")
    req = urlrequest.Request(url, data=payload, headers=headers, method="POST")
    with urlrequest.urlopen(req, timeout=120) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            text = delta.get("content")
            if text:
                yield text


_CHAT_SYSTEM = (
    "You are BauPass, an enterprise workforce operations assistant for construction sites. "
    "Answer in the same language as the user's question (German, English, or Arabic). "
    "Use ONLY the JSON context — never invent workers, counts, or alerts. "
    "Format: short title, then bullet points; end with 'Empfohlene Maßnahmen' (or equivalent) "
    "with 1–3 concrete actions when relevant. If data is missing, say so clearly."
)

_BRIEFING_SYSTEM = (
    "You are BauPass operations lead. Produce a concise daily site briefing from the JSON context. "
    "Use the user's language. Sections: Lage / On-site, Sicherheit, Anwesenheit & Risiko, "
    "Empfohlene Maßnahmen (numbered). Max 12 bullets total. No invented data."
)


def natural_language_query(
    company_id: str,
    question: str,
    context: dict[str, Any] | None = None,
    *,
    mode: str = "chat",
    lang: str = "de",
) -> dict[str, Any]:
    if not is_ai_configured():
        return {
            "answer": None,
            "configured": False,
            "hint": "Set OPENAI_API_KEY or AZURE_OPENAI_API_KEY (+ AZURE_OPENAI_ENDPOINT) on the server.",
        }

    system = _BRIEFING_SYSTEM if mode == "briefing" else _CHAT_SYSTEM
    user_content = json.dumps(
        {
            "question": question,
            "mode": mode,
            "lang": lang,
            "context": context or {},
            "company_id": company_id,
        },
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
        from .context_builder import infer_context_sources

        out: dict[str, Any] = {
            "answer": answer,
            "configured": True,
            "model": model,
            "mode": mode,
            "sources": infer_context_sources(context or {}),
        }
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


def generate_operations_briefing(
    company_id: str,
    context: dict[str, Any],
    *,
    lang: str = "de",
) -> dict[str, Any]:
    from .context_builder import deterministic_briefing

    question = {
        "de": "Erstelle das Tagesbriefing für diese Firma.",
        "en": "Create today's operations briefing for this company.",
        "ar": "أنشئ ملخص عمليات اليوم لهذه الشركة.",
    }.get(lang[:2], "Erstelle das Tagesbriefing für diese Firma.")

    if not is_ai_configured():
        return {
            "answer": deterministic_briefing(context, lang),
            "configured": False,
            "mode": "briefing",
            "source": "deterministic",
        }
    result = natural_language_query(
        company_id, question, context, mode="briefing", lang=lang
    )
    result["mode"] = "briefing"
    if not result.get("answer"):
        result["answer"] = deterministic_briefing(context, lang)
        result["source"] = "deterministic"
    return result
