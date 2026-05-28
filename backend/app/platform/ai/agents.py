"""Specialized AI agent profiles for BauPass workforce operations."""
from __future__ import annotations

from typing import Any

AGENT_PROFILES: dict[str, dict[str, Any]] = {
    "operations": {
        "id": "operations",
        "labelDe": "Betriebsleitung",
        "labelEn": "Operations lead",
        "labelAr": "قيادة التشغيل",
        "icon": "ops",
        "descriptionDe": "Anwesenheit, Tore, Baustellen-Aktivität, Tageslage",
        "tools": [
            "get_on_site_workers",
            "get_site_intelligence",
            "get_access_timeline_today",
            "get_operational_insights",
            "search_workers",
        ],
        "system": (
            "You are BauPass Operations Lead AI for construction workforce management. "
            "Focus on who is on site, gate flow, site activity, and actionable ops steps. "
            "Use tools to fetch live data before answering. Never invent counts or names."
        ),
    },
    "security": {
        "id": "security",
        "labelDe": "Sicherheit",
        "labelEn": "Security analyst",
        "labelAr": "تحليل الأمن",
        "icon": "shield",
        "descriptionDe": "Betrug, Anomalien, Alerts, Hochfrequenz-Taps",
        "tools": [
            "get_security_summary",
            "get_fraud_signals",
            "get_access_timeline_today",
            "search_workers",
            "get_worker_profile",
        ],
        "system": (
            "You are BauPass Security Analyst AI. Investigate fraud signals, open alerts, "
            "and suspicious access patterns. Prioritize high-severity items. "
            "Recommend concrete containment steps. Use tools — no fabricated incidents."
        ),
    },
    "compliance": {
        "id": "compliance",
        "labelDe": "Compliance",
        "labelEn": "Compliance officer",
        "labelAr": "الامتثال",
        "icon": "doc",
        "descriptionDe": "Dokumente, Sperren, Workforce-Risiko",
        "tools": [
            "get_expired_documents",
            "get_workforce_risk",
            "search_workers",
            "get_worker_profile",
            "get_attendance_risk",
        ],
        "system": (
            "You are BauPass Compliance AI. Focus on expired documents, locked workers, "
            "and regulatory workforce risk. Be precise about worker ids and expiry dates from tools only."
        ),
    },
    "hr": {
        "id": "hr",
        "labelDe": "HR / Belegschaft",
        "labelEn": "HR workforce",
        "labelAr": "الموارد البشرية",
        "icon": "people",
        "descriptionDe": "Mitarbeiter suchen, Profile, Anwesenheitsrisiko",
        "tools": [
            "search_workers",
            "get_worker_profile",
            "get_attendance_risk",
            "get_on_site_workers",
        ],
        "system": (
            "You are BauPass HR Workforce AI. Help find workers, explain profiles, "
            "attendance patterns and on-site status. Respect privacy — only company-scoped data."
        ),
    },
    "executive": {
        "id": "executive",
        "labelDe": "Geschäftsführung",
        "labelEn": "Executive summary",
        "labelAr": "ملخص تنفيذي",
        "icon": "chart",
        "descriptionDe": "KPIs, Risiko, Prioritäten auf einen Blick",
        "tools": [
            "get_operational_insights",
            "get_on_site_workers",
            "get_security_summary",
            "get_workforce_risk",
            "get_site_intelligence",
        ],
        "system": (
            "You are BauPass Executive Briefing AI. Provide concise KPI-style summaries "
            "for leadership: on-site headcount, risk level, security exposure, top priorities. "
            "Max 8 bullets. Use tools first."
        ),
    },
}


def list_agents(lang: str = "de") -> list[dict[str, Any]]:
    lang = lang[:2]
    out = []
    for agent in AGENT_PROFILES.values():
        label = agent.get(f"label{lang.capitalize()}") or agent["labelDe"]
        desc = agent.get(f"description{lang.capitalize()}") or agent.get("descriptionDe", "")
        out.append(
            {
                "id": agent["id"],
                "label": label,
                "description": desc,
                "icon": agent.get("icon"),
                "toolCount": len(agent.get("tools") or []),
            }
        )
    return out


def get_agent(agent_id: str) -> dict[str, Any] | None:
    return AGENT_PROFILES.get(agent_id) or AGENT_PROFILES.get("operations")


def agent_tool_schemas(agent_id: str) -> list[dict[str, Any]]:
    from .tools import OPENAI_TOOL_SCHEMAS

    agent = get_agent(agent_id) or AGENT_PROFILES["operations"]
    allowed = set(agent.get("tools") or [])
    return [t for t in OPENAI_TOOL_SCHEMAS if t["function"]["name"] in allowed]


def agent_system_prompt(agent_id: str, lang: str = "de") -> str:
    agent = get_agent(agent_id) or AGENT_PROFILES["operations"]
    base = agent["system"]
    lang_hint = {
        "de": "Antworte auf Deutsch.",
        "en": "Answer in English.",
        "ar": "أجب بالعربية.",
    }.get(lang[:2], "Antworte in der Sprache der Nutzerfrage.")
    return (
        f"{base} {lang_hint} "
        "Format: title, bullets, then 'Empfohlene Maßnahmen' (or equivalent) with 1–3 actions. "
        "When you used tools, mention which data you relied on."
    )
