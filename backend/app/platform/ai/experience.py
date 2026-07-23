"""Experience layer — turn insights into navigable, executable next steps."""
from __future__ import annotations

from typing import Any

_CARD_ACTIONS: dict[str, list[dict[str, str]]] = {
    "emergency": [
        {"type": "navigate", "url": "/index.html", "labelDe": "Notfall-Center", "labelEn": "Emergency center", "labelAr": "مركز الطوارئ"},
        {"type": "prompt", "promptDe": "Beschreibe den aktiven Notfall und empfohlene Sofortmaßnahmen.", "promptEn": "Describe the active emergency and immediate actions.", "promptAr": "صف حالة الطوارئ النشطة والإجراءات الفورية."},
        {"type": "analyze", "topic": "operations", "labelDe": "KI-Analyse", "labelEn": "AI analysis", "labelAr": "تحليل AI"},
    ],
    "security": [
        {"type": "navigate", "url": "/admin-v2/index.html#operations", "labelDe": "Sicherheit öffnen", "labelEn": "Open security", "labelAr": "فتح الأمن"},
        {"type": "analyze", "topic": "security", "labelDe": "Security Deep-Dive", "labelEn": "Security deep dive", "labelAr": "تحليل أمني"},
        {"type": "prompt", "labelDe": "KI: Security-Alerts", "labelEn": "AI: Security alerts", "labelAr": "AI: تنبيهات الأمن", "promptDe": "Welche Sicherheitsalerts sind offen und wie priorisieren?", "promptEn": "Which security alerts are open and how to prioritize?", "promptAr": "ما التنبيهات الأمنية المفتوحة؟"},
    ],
    "onsite": [
        {"type": "navigate", "url": "/foreman.html", "labelDe": "Vorarbeiter-Dashboard", "labelEn": "Foreman dashboard", "labelAr": "لوحة المشرف"},
        {"type": "navigate", "url": "/ops-command-center.html", "labelDe": "Ops Live", "labelEn": "Ops live", "labelAr": "عمليات مباشرة"},
        {"type": "prompt", "labelDe": "KI: Wer ist vor Ort?", "labelEn": "AI: Who is on site?", "labelAr": "AI: من في الموقع؟", "promptDe": "Wer ist gerade auf der Baustelle und gibt es Engpässe?", "promptEn": "Who is on site now and are there bottlenecks?", "promptAr": "من على الموقع الآن؟"},
    ],
    "risk": [
        {"type": "analyze", "topic": "compliance", "labelDe": "Compliance prüfen", "labelEn": "Check compliance", "labelAr": "فحص الامتثال"},
        {"type": "navigate", "url": "/index.html#workers", "labelDe": "Mitarbeiter", "labelEn": "Workers", "labelAr": "الموظفون"},
    ],
    "attendance": [
        {"type": "analyze", "topic": "attendance", "labelDe": "Anwesenheit analysieren", "labelEn": "Analyze attendance", "labelAr": "تحليل الحضور"},
        {"type": "prompt", "labelDe": "KI: Ausfallrisiko", "labelEn": "AI: Absence risk", "labelAr": "AI: خطر الغياب", "promptDe": "Welche Mitarbeiter haben Ausfallrisiko in den nächsten 7 Tagen?", "promptEn": "Which workers are at no-show risk in the next 7 days?", "promptAr": "من معرض لخطر الغياب؟"},
    ],
    "fraud": [
        {"type": "analyze", "topic": "security", "labelDe": "Betrug prüfen", "labelEn": "Investigate fraud", "labelAr": "تحقيق احتيال"},
        {"type": "navigate", "url": "/admin-v2/index.html#access", "labelDe": "Zutrittslogs", "labelEn": "Access logs", "labelAr": "سجلات الدخول"},
    ],
    "productivity": [
        {"type": "analyze", "topic": "operations", "labelDe": "Betrieb analysieren", "labelEn": "Operations analysis", "labelAr": "تحليل تشغيلي"},
        {"type": "prompt", "promptDe": "Wie war die Produktivität heute vs. gestern?", "promptEn": "How was productivity today vs yesterday?", "promptAr": "كيف كانت الإنتاجية اليوم؟"},
    ],
    "tomorrow": [
        {"type": "navigate", "url": "/foreman.html", "labelDe": "Vorarbeiter: Planung", "labelEn": "Foreman planning", "labelAr": "تخطيط المشرف"},
        {"type": "navigate", "url": "/ops-command-center.html", "labelDe": "Ops Center", "labelEn": "Ops center", "labelAr": "مركز العمليات"},
        {"type": "prompt", "promptDe": "Erstelle einen Personalplan für morgen inkl. Ausfallrisiken und Kontaktliste.", "promptEn": "Create a staffing plan for tomorrow including absence risks.", "promptAr": "أنشئ خطة توظيف للغد مع مخاطر الغياب."},
    ],
}

_RECOMMENDATIONS: dict[str, dict[str, str]] = {
    "review_security_findings": {
        "labelDe": "Sicherheitsbefunde bearbeiten",
        "labelEn": "Review security findings",
        "labelAr": "مراجعة نتائج الأمن",
        "type": "analyze",
        "topic": "security",
    },
    "contact_at_risk_workers": {
        "labelDe": "Ausfallrisiko: Kontaktliste",
        "labelEn": "Contact at-risk workers",
        "labelAr": "التواصل مع المعرضين للغياب",
        "type": "prompt",
        "promptDe": "Liste Mitarbeiter mit Ausfallrisiko und schlage Kontaktmaßnahmen vor.",
        "promptEn": "List at-risk workers and suggest contact actions.",
        "promptAr": "اذكر المعرضين لخطر الغياب.",
    },
    "investigate_low_activity_sites": {
        "labelDe": "Baustellen mit wenig Aktivität",
        "labelEn": "Investigate low-activity sites",
        "labelAr": "مواقع قليلة النشاط",
        "type": "analyze",
        "topic": "operations",
    },
    "manage_active_emergency": {
        "labelDe": "Notfall steuern",
        "labelEn": "Manage emergency",
        "labelAr": "إدارة الطوارئ",
        "type": "navigate",
        "url": "/index.html",
    },
    "renew_expired_documents": {
        "labelDe": "Abgelaufene Dokumente",
        "labelEn": "Renew expired documents",
        "labelAr": "تجديد الوثائق",
        "type": "analyze",
        "topic": "compliance",
    },
    "plan_tomorrow_staffing": {
        "labelDe": "Personalplan morgen",
        "labelEn": "Plan tomorrow staffing",
        "labelAr": "تخطيط الغد",
        "type": "prompt",
        "promptDe": "Welche Maßnahmen für morgen wegen Ausfallrisiko und Urlaub?",
        "promptEn": "What actions for tomorrow given absence risk and leave?",
        "promptAr": "ما الإجراءات للغد بسبب الغياب والإجازات؟",
    },
    "notify_foreman": {
        "labelDe": "Vorarbeiter informieren",
        "labelEn": "Notify foreman",
        "labelAr": "إبلاغ المشرف",
        "type": "navigate",
        "url": "/foreman.html",
    },
    "shift_coverage_review": {
        "labelDe": "Schichtabdeckung prüfen",
        "labelEn": "Review shift coverage",
        "labelAr": "مراجعة تغطية الورديات",
        "type": "navigate",
        "url": "/foreman.html",
    },
}


def _localized(item: dict[str, str], lang: str, prefix: str) -> str:
    suffix = {"de": "De", "en": "En", "ar": "Ar"}.get((lang or "de")[:2], "De")
    return (
        item.get(f"{prefix}{suffix}")
        or item.get(f"{prefix}De")
        or item.get(f"{prefix}En")
        or item.get(f"{prefix}Ar")
        or ""
    )


def enrich_insights_dashboard(dash: dict[str, Any], *, company_id: str, lang: str = "de") -> dict[str, Any]:
    """Attach per-card and playbook next actions for Command Center UI."""
    lang = (lang or "de")[:2]
    qs = f"company_id={company_id}&lang={lang}" if company_id else f"lang={lang}"

    for card in dash.get("cards") or []:
        cid = card.get("id") or ""
        raw_actions = _CARD_ACTIONS.get(cid, [])
        actions: list[dict[str, Any]] = []
        for a in raw_actions:
            act: dict[str, Any] = {"type": a["type"]}
            if a["type"] == "navigate":
                act["url"] = a["url"]
                act["label"] = _localized(a, lang, "label")
            elif a["type"] == "analyze":
                act["topic"] = a.get("topic", "operations")
                act["label"] = _localized(a, lang, "label")
            elif a["type"] == "prompt":
                act["prompt"] = _localized(a, lang, "prompt")
                # Prefer a short button label; keep full text in prompt.
                short = _localized(a, lang, "label")
                act["label"] = short or (act["prompt"][:42] + ("…" if len(act["prompt"]) > 42 else ""))
            actions.append(act)
        card["actions"] = actions

    next_actions: list[dict[str, Any]] = []
    for rec in dash.get("recommendations") or []:
        spec = _RECOMMENDATIONS.get(rec)
        if not spec:
            continue
        item: dict[str, Any] = {
            "id": rec,
            "type": spec["type"],
            "label": _localized(spec, lang, "label"),
        }
        if spec["type"] == "navigate":
            item["url"] = spec.get("url", "/ai-command-center.html")
        elif spec["type"] == "analyze":
            item["topic"] = spec.get("topic", "operations")
        elif spec["type"] == "prompt":
            item["prompt"] = _localized(spec, lang, "prompt")
        next_actions.append(item)

    if not next_actions and int((dash.get("snapshot") or {}).get("openSecurityFindings") or 0) > 0:
        next_actions.append(
            {
                "id": "default_security",
                "type": "analyze",
                "topic": "security",
                "label": _localized(_RECOMMENDATIONS["review_security_findings"], lang, "label"),
            }
        )

    # Always offer a few working AI prompts — even when metrics are zero.
    if not next_actions:
        next_actions.extend(
            [
                {
                    "id": "default_onsite",
                    "type": "prompt",
                    "label": _localized(_CARD_ACTIONS["onsite"][2], lang, "label") or "KI: Wer ist vor Ort?",
                    "prompt": _localized(_CARD_ACTIONS["onsite"][2], lang, "prompt"),
                },
                {
                    "id": "default_security_prompt",
                    "type": "prompt",
                    "label": _localized(_CARD_ACTIONS["security"][2], lang, "label") or "KI: Security",
                    "prompt": _localized(_CARD_ACTIONS["security"][2], lang, "prompt"),
                },
                {
                    "id": "default_attendance",
                    "type": "analyze",
                    "topic": "attendance",
                    "label": _localized(_CARD_ACTIONS["attendance"][0], lang, "label"),
                },
            ]
        )

    dash["nextActions"] = next_actions[:6]
    dash["playbookUrl"] = f"/ai-command-center.html?{qs}"
    dash["opsUrl"] = f"/ops-command-center.html?{qs}"
    return dash
