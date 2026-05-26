"""
AI assistant scaffold — enable with OPENAI_API_KEY or Azure OpenAI env vars.
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib import request as urlrequest


def is_ai_configured() -> bool:
    return bool(
        os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    )


def natural_language_query(company_id: int, question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    if not is_ai_configured():
        return {
            "answer": None,
            "configured": False,
            "hint": "Set OPENAI_API_KEY or AZURE_OPENAI_API_KEY to enable the AI assistant.",
        }
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("BAUPASS_AI_MODEL", "gpt-4o-mini")
    system = (
        "You are BauPass workforce assistant. Answer briefly in the user's language. "
        "Use only the provided JSON context; do not invent employee data."
    )
    user_content = json.dumps({"question": question, "context": context or {}, "company_id": company_id}, ensure_ascii=False)
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    req = urlrequest.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    answer = body["choices"][0]["message"]["content"]
    return {"answer": answer, "configured": True, "model": model}
