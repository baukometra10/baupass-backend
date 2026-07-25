"""Specialized AI agent profiles for SUPPIX workforce operations."""
from __future__ import annotations

from typing import Any

AGENT_PROFILES: dict[str, dict[str, Any]] = {
    "admin": {
        "id": "admin",
        "labelDe": "Admin-Betriebsleiter",
        "labelEn": "Admin operations lead",
        "labelAr": "قيادة تشغيل الإدارة",
        "icon": "ops",
        "descriptionDe": "Vollständiger Admin-Operator mit allen Live-Tools",
        "tools": [
            "get_on_site_workers",
            "get_site_intelligence",
            "get_access_timeline_today",
            "get_operational_insights",
            "search_workers",
            "get_worker_profile",
            "get_tomorrow_forecast",
            "get_repeated_late_workers",
            "get_outside_hours_attempts",
            "get_presence_summary",
            "browse_inbox",
            "get_deployment_month_status",
            "get_expired_documents",
            "get_security_summary",
            "get_fraud_signals",
            "get_attendance_risk",
            "get_workforce_risk",
        ],
        "system": (
            "Du bist der erweiterte WorkPass ADMIN-Betriebsassistent — deutlich leistungsfähiger "
            "als die Standard-Unternehmensansicht. Du hast Zugang zu allen Live-Tools "
            "(Anwesenheit, Risiko, Security, Fraud, Forecast, Inbox, Einsatzplan, Profile). "
            "Arbeite präzise, priorisiere Handlungsbedarf, schlage genehmigungspflichtige Aktionen "
            "nur mit klarer Evidenz vor. Nutze Fachsprache des Betriebssektors. "
            "Schreiben/Push/Broadcast nur nach expliziter Bestätigung."
        ),
    },
    "operations": {
        "id": "operations",
        "labelDe": "Betriebsleitung",
        "labelEn": "Operations lead",
        "labelAr": "قيادة التشغيل",
        "icon": "ops",
        "descriptionDe": "Anwesenheit, Tore, Standort-Aktivität, Tageslage",
        "tools": [
            "get_on_site_workers",
            "get_site_intelligence",
            "get_access_timeline_today",
            "get_operational_insights",
            "search_workers",
            "get_tomorrow_forecast",
            "get_repeated_late_workers",
            "get_outside_hours_attempts",
            "get_presence_summary",
            "browse_inbox",
            "get_deployment_month_status",
            "get_expired_documents",
            "get_security_summary",
            "get_fraud_signals",
            "get_attendance_risk",
            "get_workforce_risk",
            "get_worker_profile",
        ],
        "system": (
            "Du bist der WorkPass Betriebsleiter-Assistent für Standorte und Zutrittskontrolle. "
            "Du kennst Anwesenheit, Tore, Live-Aktivität und tagesaktuelle Engpässe. "
            "Nutze die Fachsprache des Betriebssektors aus dem Kontext (z. B. Standort-/Personalbegriffe). "
            "Nutze Forecast, Verspätungs-Streaks, Outside-Hours-Versuche und Inbox für konkrete Entscheidungen. "
            "Für Einsatzpläne: zuerst get_deployment_month_status lesen; Vorbereiten/Senden nur als "
            "genehmigungspflichtige Aktionen vorschlagen (prepare_deployment_month / confirm_send_deployment_month). "
            "Du bist der ubiquitäre Betriebs-Assistent: Tageslage, Anwesenheit, Forecast, Outside-Hours, "
            "Inbox, Dokumente, Security und Navigation (Verträge/Docs/Chat/Mitarbeiter) abdecken. "
            "Schreiben/Push/Broadcast nur nach expliziter Bestätigung."
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
            "get_outside_hours_attempts",
            "browse_inbox",
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
            "get_repeated_late_workers",
            "browse_inbox",
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
        "descriptionDe": "Personal suchen, Profile, Anwesenheitsrisiko",
        "tools": [
            "search_workers",
            "get_worker_profile",
            "get_attendance_risk",
            "get_on_site_workers",
            "get_repeated_late_workers",
            "get_tomorrow_forecast",
            "get_presence_summary",
            "get_deployment_month_status",
        ],
        "system": (
            "Du bist der SUPPIX HR-Assistent für Belegschaft und Anwesenheit. "
            "Du findest Personen im Personalstamm, erklärst Profile und Anwesenheitsmuster. "
            "Verwende die sektorspezifischen Bezeichnungen aus dem Live-Kontext. "
            "Einsatzplan-Status über get_deployment_month_status; Schreiben nur nach Freigabe."
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
            "get_tomorrow_forecast",
            "get_repeated_late_workers",
            "browse_inbox",
        ],
        "system": (
            "Du bist der SUPPIX Executive-Assistent für die Geschäftsführung. "
            "Du fasst KPIs, Risiken und Prioritäten knapp zusammen."
        ),
    },
    "decision": {
        "id": "decision",
        "labelDe": "Entscheidungsassistent",
        "labelEn": "Decision assistant",
        "labelAr": "مساعد القرارات",
        "icon": "decision",
        "descriptionDe": "Lage bewerten, Empfehlung + genehmigungspflichtige Aktionen",
        "tools": [
            "get_tomorrow_forecast",
            "get_repeated_late_workers",
            "get_outside_hours_attempts",
            "get_presence_summary",
            "browse_inbox",
            "get_operational_insights",
            "get_on_site_workers",
            "get_security_summary",
            "get_workforce_risk",
            "search_workers",
            "get_deployment_month_status",
        ],
        "system": (
            "Du bist der WorkPass Entscheidungsassistent. "
            "Liefere klare Empfehlungen mit Evidenz aus Tools. "
            "Schlage nur Aktionen vor, die ein Mensch freigeben muss "
            "(notify_worker, resolve_security_alert, approve_leave_request, reject_leave_request, "
            "ack_system_alert, send_briefing_email, prepare_deployment_month, confirm_send_deployment_month, "
            "remind_expired_documents, remind_late_workers, resolve_open_security_alerts, "
            "ack_open_system_alerts, broadcast_worker_message). "
            "confirm_send_deployment_month und broadcast_worker_message sind kritisch (Massenversand) — "
            "nur nach Prüfung vorschlagen. "
            "Antworte zusätzlich als JSON-Block DECISION_JSON={...} mit keys: "
            "summary, recommendation, confidence (0-1), rationale, evidence (list of {tool,key,value}), "
            "proposedActions (list of {action,params,labelDe,risk})."
        ),
    },
}

_CONVERSATION_RULES: dict[str, str] = {
    "de": (
        "Kommuniziere natürlich und direkt — wie mit einer erfahrenen Kollegin vor Ort. "
        "Verstehe auch umgangssprachliches Deutsch, kurze Nachrichten, Tippfehler und Nachfragen. "
        "Beziehe den Chat-Verlauf ein; bei mehrdeutigen Fragen stelle eine kurze Rückfrage. "
        "Nutze Tools für aktuelle Live-Daten, wenn die Frage konkrete Zahlen, Namen oder Listen braucht. "
        "Erfinde niemals Personen, Zähler oder Vorfälle. "
        "Nutze die Fachbegriffe des Betriebssektors aus dem Kontext. "
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
        "تواصل بشكل طبيعي ومباشر مع مسؤول النظام. "
        "افهم العربية الفصحى وجميع اللهجات الشائعة (مصرية، شامية، خليجية، مغاربية، عراقية…) "
        "والأسئلة القصيرة والعامية والمتابعة. لا تطلب من المستخدم التحدث بلهجة معيّنة. "
        "أجب بفصحى مبسطة واضحة إلا إذا كان أسلوب المستخدم لهجياً بوضوح فقارب أسلوبه بلطف. "
        "استخدم الأدوات للبيانات الحية عند الحاجة. لا تخترع أسماء أو أرقام."
    ),
    "tr": (
        "Doğal ve doğrudan konuş — sahadaki deneyimli bir meslektaş gibi. "
        "Gündelik Türkçe, kısa mesajlar ve yazım hatalarını anla. "
        "Canlı veri için araçları kullan; kişi, sayı veya olay uydurma."
    ),
    "fr": (
        "Communique de façon naturelle et directe, comme un collègue de chantier expérimenté. "
        "Comprends le français courant, les messages courts et les fautes de frappe. "
        "Utilise les outils pour les données live; n'invente jamais de personnes ni de chiffres."
    ),
    "es": (
        "Comunica de forma natural y directa, como un compañero experimentado en obra. "
        "Entiende el español cotidiano, mensajes cortos y erratas. "
        "Usa herramientas para datos en vivo; no inventes personas ni cifras."
    ),
    "it": (
        "Comunica in modo naturale e diretto, come un collega esperto in cantiere. "
        "Capisci l'italiano colloquiale, messaggi brevi e refusi. "
        "Usa i tool per i dati live; non inventare persone o numeri."
    ),
    "pl": (
        "Komunikuj się naturalnie i bezpośrednio — jak doświadczony kolega na budowie. "
        "Rozumiej potoczny polski, krótkie wiadomości i literówki. "
        "Używaj narzędzi do danych na żywo; nie wymyślaj osób ani liczb."
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
        "وضع الصوت (مثل ChatGPT Voice): المستخدم تحدّث بسؤاله — قد تكون لهجته عامية. "
        "افهم اللهجة كما هي وأجب على السؤال فقط — مباشرة وبوضوح وبلطف. "
        "استخدم عربية فصحى مبسطة سهلة النطق (أو قرّب أسلوب المستخدم إن كان لهجياً). "
        "بدون Markdown أو قوائم أو جداول أو ذكر للمصادر في النص. "
        "2–6 جمل واضحة تغطي الإجابة للمحادثة الصوتية."
    ),
    "tr": (
        "SES MODU: Kullanıcı soruyu konuşarak sordu. "
        "Sadece soruya cevap ver — doğrudan, sıcak, net. "
        "Markdown, madde listesi, tablo veya kaynak/tool adı yok. "
        "2–6 kısa, doğal konuşma cümlesi."
    ),
    "fr": (
        "MODE VOCAL: L'utilisateur a parlé. "
        "Réponds UNIQUEMENT à la question — direct, amical, clair. "
        "Pas de markdown, listes, tableaux ni mentions d'outils. "
        "2–6 phrases orales naturelles."
    ),
    "es": (
        "MODO VOZ: El usuario habló. "
        "Responde SOLO a la pregunta — directo, amable, claro. "
        "Sin markdown, listas, tablas ni menciones de herramientas. "
        "2–6 frases orales naturales."
    ),
    "it": (
        "MODALITÀ VOCALE: L'utente ha parlato. "
        "Rispondi SOLO alla domanda — diretto, cordiale, chiaro. "
        "Niente markdown, elenchi, tabelle o menzioni di tool. "
        "2–6 frasi parlate naturali."
    ),
    "pl": (
        "TRYB GŁOSOWY: Użytkownik mówił. "
        "Odpowiedz TYLKO na pytanie — bezpośrednio, przyjaźnie, jasno. "
        "Bez markdown, list, tabel i wzmianek o narzędziach. "
        "2–6 krótkich naturalnych zdań mówionych."
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
    from .langs import normalize_ui_lang, reply_language_instruction

    agent = get_agent(agent_id) or AGENT_PROFILES["operations"]
    lang = normalize_ui_lang(lang)
    parts = [
        ai_branding_system_block(lang),
        agent["system"],
        _CONVERSATION_RULES.get(lang) or _CONVERSATION_RULES["en"],
        reply_language_instruction(lang),
    ]
    if spoken:
        parts.append(_SPOKEN_MODE_RULES.get(lang) or _SPOKEN_MODE_RULES["en"])
    if live_context.strip():
        parts.append("Aktueller System-Kontext (Snapshot — bei Bedarf Tools für frische Daten nutzen):\n" + live_context.strip())
    return "\n\n".join(parts)
