"""Agent runner — OpenAI tool-calling loop with specialized BauPass agents."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Generator

from .agents import agent_system_prompt, agent_tool_schemas, get_agent
from .assistant import is_ai_configured, resolve_ai_model
from .context_builder import build_compact_context, infer_context_sources
from .tools import run_tool

logger = logging.getLogger("baupass.ai.agent")

MAX_TOOL_ROUNDS = int(os.getenv("BAUPASS_AI_MAX_TOOL_ROUNDS", "6"))


def _chat_with_tools(messages: list[dict], tools: list[dict]) -> dict[str, Any]:
    from .assistant import _chat_completion

    return _chat_completion(messages, tools=tools, tool_choice="auto")


def run_agent_query(
    db,
    company_id: str,
    question: str,
    *,
    agent_id: str = "operations",
    lang: str = "de",
    role: str = "company-admin",
    history: list[dict] | None = None,
) -> dict[str, Any]:
    if not is_ai_configured():
        return {
            "answer": None,
            "configured": False,
            "agentId": agent_id,
            "hint": "OPENAI_API_KEY nicht konfiguriert.",
        }

    agent = get_agent(agent_id)
    if not agent:
        agent_id = "operations"
        agent = get_agent("operations")

    from .actions import suggest_actions
    from .rag import search_knowledge

    ctx = build_compact_context(db, company_id, role)
    rag_chunks = search_knowledge(db, company_id, question)
    if rag_chunks:
        ctx["ragChunks"] = rag_chunks
    tools = agent_tool_schemas(agent_id)
    model, config_warning = resolve_ai_model()

    system = agent_system_prompt(agent_id, lang)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "company_id": company_id,
                    "baseline_context": ctx,
                    "rag_chunks": rag_chunks,
                    "instruction": "Use tools for fresh data when the question needs specifics. Use rag_chunks for document context.",
                },
                ensure_ascii=False,
            ),
        },
    ]
    for h in (history or [])[-12:]:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)[:4000]})

    messages.append({"role": "user", "content": question})

    tools_used: list[str] = []
    tool_rounds = 0

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            body = _chat_with_tools(messages, tools)
            choice = body["choices"][0]
            msg = choice["message"]
            tool_calls = msg.get("tool_calls") or []

            if tool_calls:
                tool_rounds += 1
                messages.append(msg)
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    name = fn.get("name", "")
                    args_raw = fn.get("arguments") or "{}"
                    result = run_tool(db, company_id, name, args_raw)
                    tools_used.append(name)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id"),
                            "content": json.dumps(result, ensure_ascii=False)[:12000],
                        }
                    )
                continue

            answer = msg.get("content") or ""
            out: dict[str, Any] = {
                "answer": answer,
                "configured": True,
                "agentId": agent_id,
                "model": model,
                "mode": "agent",
                "toolsUsed": list(dict.fromkeys(tools_used)),
                "toolRounds": tool_rounds,
                "sources": infer_context_sources(ctx) + [f"tool:{t}" for t in tools_used],
            }
            if config_warning:
                out["configWarning"] = config_warning
            out["ragChunks"] = len(rag_chunks)
            out["suggestedActions"] = suggest_actions(ctx, company_id=company_id, tools_used=tools_used)
            return out

        return {
            "answer": None,
            "error": "tool_loop_exhausted",
            "hint": "KI hat zu viele Tool-Schritte benötigt. Frage vereinfachen.",
            "toolsUsed": tools_used,
            "agentId": agent_id,
        }
    except Exception as exc:
        logger.exception("agent_query failed company=%s agent=%s", company_id, agent_id)
        return {
            "answer": None,
            "configured": True,
            "error": "agent_failed",
            "hint": str(exc)[:500],
            "agentId": agent_id,
        }


def run_agent_query_stream(
    db,
    company_id: str,
    question: str,
    *,
    agent_id: str = "operations",
    lang: str = "de",
    role: str = "company-admin",
    history: list[dict] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Yield progress events, then stream final answer tokens via OpenAI."""
    from .assistant import is_ai_configured

    if not is_ai_configured():
        yield {"type": "error", "hint": "OPENAI_API_KEY nicht konfiguriert."}
        yield {"type": "done", "ok": False}
        return

    yield {"type": "start", "agentId": agent_id}

    agent = get_agent(agent_id)
    if not agent:
        agent_id = "operations"
        agent = get_agent("operations")
    agent_id = agent["id"]
    from .actions import suggest_actions
    from .rag import search_knowledge

    ctx = build_compact_context(db, company_id, role)
    rag_chunks = search_knowledge(db, company_id, question)
    if rag_chunks:
        ctx["ragChunks"] = rag_chunks
    tools = agent_tool_schemas(agent_id)
    model, config_warning = resolve_ai_model()
    system = agent_system_prompt(agent_id, lang)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "company_id": company_id,
                    "baseline_context": ctx,
                    "rag_chunks": rag_chunks,
                    "instruction": "Use tools for fresh data when needed.",
                },
                ensure_ascii=False,
            ),
        },
    ]
    for h in (history or [])[-12:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])[:4000]})
    messages.append({"role": "user", "content": question})

    tools_used: list[str] = []
    try:
        from .assistant import _stream_chat_completion_events

        for _ in range(MAX_TOOL_ROUNDS):
            content_deltas: list[str] = []
            tool_msg: dict[str, Any] | None = None
            live_answer = False
            for ev in _stream_chat_completion_events(messages, tools=tools):
                if ev["type"] == "tool_calls":
                    tool_msg = ev["message"]
                    if live_answer:
                        yield {"type": "answer_reset"}
                        live_answer = False
                    break
                if ev["type"] == "content_delta":
                    text = ev.get("text") or ""
                    if not text:
                        continue
                    content_deltas.append(text)
                    if not live_answer:
                        yield {"type": "answer_start"}
                        live_answer = True
                    yield {"type": "chunk", "text": text}

            tool_calls = (tool_msg or {}).get("tool_calls") or []
            if tool_calls:
                preamble = "".join(content_deltas).strip()
                if preamble and not live_answer:
                    yield {"type": "status", "text": preamble[:400]}
                messages.append(tool_msg)
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    name = fn.get("name", "")
                    yield {"type": "tool_start", "tool": name}
                    result = run_tool(db, company_id, name, fn.get("arguments") or "{}")
                    tools_used.append(name)
                    yield {"type": "tool_done", "tool": name, "ok": "error" not in result}
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id"),
                            "content": json.dumps(result, ensure_ascii=False)[:12000],
                        }
                    )
                continue

            if not live_answer:
                yield {"type": "answer_start"}
                for part in content_deltas:
                    yield {"type": "chunk", "text": part}
            answer = "".join(content_deltas)
            suggested = suggest_actions(ctx, company_id=company_id, tools_used=tools_used)
            yield {
                "type": "done",
                "ok": True,
                "answer": answer,
                "agentId": agent_id,
                "model": model,
                "toolsUsed": list(dict.fromkeys(tools_used)),
                "sources": infer_context_sources(ctx) + [f"tool:{t}" for t in tools_used],
                "suggestedActions": suggested,
                "configWarning": config_warning,
                "ragChunks": len(rag_chunks),
            }
            return

        yield {"type": "error", "hint": "Tool-Schleife erschöpft.", "error": "tool_loop_exhausted"}
        yield {"type": "done", "ok": False, "toolsUsed": tools_used}
    except Exception as exc:
        logger.exception("agent stream failed")
        yield {"type": "error", "hint": str(exc)[:500]}
        yield {"type": "done", "ok": False}


def run_deep_analysis(
    db,
    company_id: str,
    topic: str,
    *,
    lang: str = "de",
    role: str = "company-admin",
) -> dict[str, Any]:
    prompts = {
        "security": {
            "de": "Führe eine vollständige Sicherheitsanalyse durch: Alerts, Betrug, Anomalien, Prioritäten.",
            "en": "Run a full security analysis: alerts, fraud, anomalies, priorities.",
            "ar": "أجرِ تحليلاً أمنياً كاملاً: التنبيهات والاحتيال والأولويات.",
            "agent": "security",
        },
        "attendance": {
            "de": "Analysiere Anwesenheit und Ausfallrisiken der letzten 14 Tage mit Maßnahmen.",
            "en": "Analyze attendance and no-show risks for the last 14 days with actions.",
            "ar": "حلّل الحضور ومخاطر الغياب لآخر 14 يوماً مع إجراءات.",
            "agent": "hr",
        },
        "compliance": {
            "de": "Compliance-Check: abgelaufene Dokumente, gesperrte Mitarbeiter, Risiko-Score.",
            "en": "Compliance check: expired documents, locked workers, risk score.",
            "ar": "فحص الامتثال: الوثائق المنتهية والموظفون الموقوفون.",
            "agent": "compliance",
        },
        "operations": {
            "de": "Vollständige Betriebsanalyse: Baustelle, Tore, Engpässe, heutige Lage.",
            "en": "Full operations analysis: site, gates, bottlenecks, today's status.",
            "ar": "تحليل تشغيلي كامل: الموقع والبوابات والاختناقات.",
            "agent": "operations",
        },
        "executive": {
            "de": "Executive Summary für die Geschäftsführung mit KPIs und Top-5 Maßnahmen.",
            "en": "Executive summary with KPIs and top 5 actions.",
            "ar": "ملخص تنفيذي مع مؤشرات و5 إجراءات.",
            "agent": "executive",
        },
    }
    spec = prompts.get(topic, prompts["operations"])
    question = spec.get(lang[:2], spec["de"])
    return run_agent_query(
        db,
        company_id,
        question,
        agent_id=spec["agent"],
        lang=lang,
        role=role,
    )
