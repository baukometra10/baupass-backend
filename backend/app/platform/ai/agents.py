"""Specialized AI agent profiles for SUPPIX workforce operations."""
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
            "Du bist der WorkPass Betriebsleiter-Assistent für Baustellen und Zutrittskontrolle. "
            "Du kennst Anwesenheit, Tore, Live-Aktivität und tagesaktuelle Engpässe."
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
            "Du bist der SUPPIX Sicherheits-Analyst. "
            "Du untersuchst Betrugs-Signale, Alerts und auffällige Zutrittsmuster."
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
            "Du bist der SUPPIX Compliance-Assistent. "
            "Du hilfst bei abgelaufenen Dokumenten, Sperren und Workforce-Risiko."
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
            "Du bist der SUPPIX HR-Assistent für Belegschaft und Anwesenheit. "
            "Du findest Mitarbeiter, erklärst Profile und Anwesenheitsmuster."
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
            "Du bist der SUPPIX Executive-Assistent für die Geschäftsführung. "
            "Du fasst KPIs, Risiken und Prioritäten knapp zusammen."
        ),
    },
}

_CONVERSATION_RULES: dict[str, str] = {
    "de": (
        "Kommuniziere natürlich und direkt — wie mit einer erfahrenen Kollegin auf der Baustelle. "
        "Verstehe auch umgangssprachliches Deutsch, kurze Nachrichten, Tippfehler und Nachfragen. "
        "Beziehe den Chat-Verlauf ein; bei mehrdeutigen Fragen stelle eine kurze Rückfrage. "
        "Nutze Tools für aktuelle Live-Daten, wenn die Frage konkrete Zahlen, Namen oder Listen braucht. "
        "Erfinde niemals Mitarbeiter, Zähler oder Vorfälle. "
        "Antworte in Prosa; nutze Aufzählungen nur wenn sie der Übersicht dienen. "
        "Bei Smalltalk oder einfachen Fragen: kurz und freundlich, ohne Report-Format."
    ),
    "en": (
        "Communicate naturally and directly, like a knowledgeable site colleague. "
        "Understand informal phrasing, short messages, typos, and follow-up questions. "
        "Use chat history; ask a brief clarifying question when ambiguous. "
        "Use tools for live data when the question needs counts, names, or lists. "
        "Never invent workers, numbers, or incidents. "
        "Answer in prose; use bullets only when they help clarity."
    ),
    "ar": (
        "تواصل بشكل طبيعي ومباشر. افهم الأسئلة العامية والمتابعة. "
        "استخدم الأدوات للبيانات الحية عند الحاجة. لا تخترع أسماء أو أرقام."
    ),
}

_SPOKEN_MODE_RULES = {
    "de": (
        "SPRACHMODUS (wie ChatGPT Voice): Der Nutzer hat gesprochen. "
        "Antworte NUR auf die gestellte Frage — direkt, freundlich, klar. "
        "Kein Markdown, keine Aufzählungen, keine Tabellen, keine Quellen- oder Tool-Hinweise im Antworttext. "
        "2–6 kurze Sätze in natürlicher gesprochener Sprache, dann aufhören."
    ),
    "en": (
        "VOICE MODE (ChatGPT Voice style): The user spoke their question. "
        "Answer ONLY the question — direct, friendly, clear. "
        "No markdown, bullet lists, tables, or source/tool mentions in the reply text. "
        "2–6 short natural spoken sentences, then stop."
    ),
    "ar": (
        "وضع الصوت (مثل ChatGPT Voice): المستخدم تحدّث بسؤاله. "
        "أجب على السؤال فقط — مباشرة وبوضوح وبلطف. "
        "استخدم العربية الفصحى البسيطة الواضحة، جمل طبيعية سهلة النطق. "
        "بدون Markdown أو قوائم أو جداول أو ذكر للمصادر في النص. "
        "4–8 جمل واضحة تغطي الإجابة كاملة للمحادثة الصوتية."
    ),
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


def agent_system_prompt(agent_id: str, lang: str = "de", *, live_context: str = "", spoken: bool = False) -> str:
    from .brand_guard import ai_branding_system_block

    agent = get_agent(agent_id) or AGENT_PROFILES["operations"]
    lang = (lang or "de")[:2]
    lang_reply = {
        "de": "Antworte auf Deutsch, es sei denn der Nutzer schreibt klar auf Englisch oder Arabisch.",
        "en": "Answer in English unless the user clearly writes in German or Arabic.",
        "ar": "أجب بالعربية ما لم يكتب المستخدم بالألمانية أو الإنجليزية.",
    }.get(lang, "Match the user's language.")
    parts = [
        ai_branding_system_block(lang),
        agent["system"],
        _CONVERSATION_RULES.get(lang) or _CONVERSATION_RULES["de"],
        lang_reply,
    ]
    if spoken:
        parts.append(_SPOKEN_MODE_RULES.get(lang) or _SPOKEN_MODE_RULES["de"])
    if live_context.strip():
        parts.append("Aktueller System-Kontext (Snapshot — bei Bedarf Tools für frische Daten nutzen):\n" + live_context.strip())
    return "\n\n".join(parts)
