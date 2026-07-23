"""Experience layer — turn insights into navigable, executable next steps."""
from __future__ import annotations

from typing import Any

_CARD_ACTIONS: dict[str, list[dict[str, str]]] = {
    "emergency": [
        {"type": "navigate", "url": "/admin-v2/index.html?tab=overview", "labelDe": "Notfall-Center", "labelEn": "Emergency center", "labelAr": "مركز الطوارئ"},
        {"type": "prompt", "promptDe": "Beschreibe den aktiven Notfall und empfohlene Sofortmaßnahmen.", "promptEn": "Describe the active emergency and immediate actions.", "promptAr": "صف حالة الطوارئ النشطة والإجراءات الفورية."},
        {"type": "analyze", "topic": "operations", "labelDe": "KI-Analyse", "labelEn": "AI analysis", "labelAr": "تحليل AI"},
    ],
    "security": [
        {"type": "navigate", "url": "/admin-v2/index.html?tab=operations", "labelDe": "Sicherheit öffnen", "labelEn": "Open security", "labelAr": "فتح الأمن"},
        {"type": "analyze", "topic": "security", "labelDe": "Security Deep-Dive", "labelEn": "Security deep dive", "labelAr": "تحليل أمني"},
        {"type": "prompt", "labelDe": "KI: Security-Alerts", "labelEn": "AI: Security alerts", "labelAr": "AI: تنبيهات الأمن", "promptDe": "Welche Sicherheitsalerts sind offen und wie priorisieren?", "promptEn": "Which security alerts are open and how to prioritize?", "promptAr": "ما التنبيهات الأمنية المفتوحة؟"},
    ],
    "onsite": [
        {"type": "navigate", "url": "/admin-v2/index.html?tab=access", "labelDe": "Anwesenheit", "labelEn": "Attendance", "labelAr": "الحضور"},
        {"type": "navigate", "url": "/ops-command-center.html", "labelDe": "Ops Live", "labelEn": "Ops live", "labelAr": "عمليات مباشرة"},
        {"type": "prompt", "labelDe": "KI: Wer ist vor Ort?", "labelEn": "AI: Who is on site?", "labelAr": "AI: من في الموقع؟", "promptDe": "Wer ist gerade auf der Baustelle und gibt es Engpässe?", "promptEn": "Who is on site now and are there bottlenecks?", "promptAr": "من على الموقع الآن؟"},
    ],
    "risk": [
        {"type": "analyze", "topic": "compliance", "labelDe": "Compliance prüfen", "labelEn": "Check compliance", "labelAr": "فحص الامتثال"},
        {"type": "navigate", "url": "/admin-v2/index.html?tab=workers", "labelDe": "Mitarbeiter", "labelEn": "Workers", "labelAr": "الموظفون"},
    ],
    "attendance": [
        {"type": "analyze", "topic": "attendance", "labelDe": "Anwesenheit analysieren", "labelEn": "Analyze attendance", "labelAr": "تحليل الحضور"},
        {"type": "prompt", "labelDe": "KI: Ausfallrisiko", "labelEn": "AI: Absence risk", "labelAr": "AI: خطر الغياب", "promptDe": "Welche Mitarbeiter haben Ausfallrisiko in den nächsten 7 Tagen?", "promptEn": "Which workers are at no-show risk in the next 7 days?", "promptAr": "من معرض لخطر الغياب؟"},
    ],
    "fraud": [
        {"type": "analyze", "topic": "security", "labelDe": "Betrug prüfen", "labelEn": "Investigate fraud", "labelAr": "تحقيق احتيال"},
        {"type": "navigate", "url": "/admin-v2/index.html?tab=access", "labelDe": "Zutrittslogs", "labelEn": "Access logs", "labelAr": "سجلات الدخول"},
    ],
    "productivity": [
        {"type": "analyze", "topic": "operations", "labelDe": "Betrieb analysieren", "labelEn": "Operations analysis", "labelAr": "تحليل تشغيلي"},
        {"type": "prompt", "promptDe": "Wie war die Produktivität heute vs. gestern?", "promptEn": "How was productivity today vs yesterday?", "promptAr": "كيف كانت الإنتاجية اليوم؟"},
    ],
    "tomorrow": [
        {"type": "navigate", "url": "/admin-v2/index.html?tab=workers&einsatzplan=1", "labelDe": "Vorarbeiter: Planung", "labelEn": "Foreman planning", "labelAr": "تخطيط المشرف"},
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
        "url": "/admin-v2/index.html?tab=overview",
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
        "url": "/admin-v2/index.html?tab=workers&einsatzplan=1",
    },
    "shift_coverage_review": {
        "labelDe": "Schichtabdeckung prüfen",
        "labelEn": "Review shift coverage",
        "labelAr": "مراجعة تغطية الورديات",
        "type": "navigate",
        "url": "/admin-v2/index.html?tab=access",
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


_ZERO_CARD_DETAILS: dict[str, dict[str, str]] = {
    "onsite": {
        "detailDe": "Niemand eingecheckt — Lage prüfen",
        "detailEn": "Nobody checked in — review site status",
        "detailAr": "لا أحد مسجّل حضوراً — راجع الوضع",
    },
    "security": {
        "detailDe": "Keine offenen Befunde — Kurzcheck möglich",
        "detailEn": "No open findings — quick check available",
        "detailAr": "لا توجد نتائج مفتوحة — يمكن فحص سريع",
    },
    "risk": {
        "detailDe": "Keine abgelaufenen Dokumente · keine Sperren",
        "detailEn": "No expired docs · no locks",
        "detailAr": "لا وثائق منتهية · لا إيقافات",
    },
    "attendance": {
        "detailDe": "Kein Ausfallrisiko erkannt — Analyse starten",
        "detailEn": "No absence risk detected — start analysis",
        "detailAr": "لا خطر غياب ظاهر — ابدأ التحليل",
    },
    "fraud": {
        "detailDe": "Keine Betrugssignale — optional prüfen",
        "detailEn": "No fraud signals — optional check",
        "detailAr": "لا إشارات احتيال — فحص اختياري",
    },
    "productivity": {
        "detailDe": "Noch keine Stempel heute",
        "detailEn": "No punches yet today",
        "detailAr": "لا طوابع حضور اليوم بعد",
    },
}


def _card_value_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (int, float)):
        return float(value) == 0
    text = str(value).strip()
    return text in {"", "0", "0/0", "—", "-"}


def _sector_vocab(terms: dict[str, str] | None, lang: str) -> tuple[str, str]:
    lang = (lang or "de")[:2]
    defaults = {
        "de": ("Mitarbeiter", "Standort"),
        "en": ("workers", "site"),
        "ar": ("عمال", "موقع"),
    }
    w_fb, s_fb = defaults.get(lang, defaults["de"])
    workers = str((terms or {}).get("termWorkers") or w_fb).strip() or w_fb
    site = str((terms or {}).get("termSite") or s_fb).strip() or s_fb
    return workers, site


def _apply_sector_text(text: str, *, workers: str, site: str, lang: str = "de") -> str:
    if not text:
        return text
    out = str(text)
    # Always rewrite German construction defaults used in shared templates.
    out = out.replace("Baustellen", site).replace("Baustelle", site).replace("Mitarbeiter", workers)
    if (lang or "de")[:2] == "en":
        if out.strip() in {"Workers", "workers"}:
            return workers
        out = out.replace("low-activity sites", f"low-activity {site} locations")
        out = out.replace("on site now", f"at {site} now").replace("Who is on site", f"Who is at {site}")
        out = out.replace("at-risk workers", f"at-risk {workers}")
    return out


def enrich_insights_dashboard(
    dash: dict[str, Any],
    *,
    company_id: str,
    lang: str = "de",
    terms: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Attach per-card and playbook next actions for Command Center UI."""
    lang = (lang or "de")[:2]
    qs = f"company_id={company_id}&lang={lang}" if company_id else f"lang={lang}"
    if terms is None and company_id:
        try:
            from backend.app.platform.sector.catalog import sector_terms_for_company
            from backend.server import get_db

            terms = sector_terms_for_company(get_db(), company_id, lang=lang)
        except Exception:
            terms = {}
    workers, site = _sector_vocab(terms, lang)

    for card in dash.get("cards") or []:
        cid = card.get("id") or ""
        if _card_value_empty(card.get("value")):
            zero = _ZERO_CARD_DETAILS.get(cid)
            if zero:
                card["detail"] = _localized(zero, lang, "detail") or card.get("detail") or ""
        raw_actions = list(_CARD_ACTIONS.get(cid, []))
        # Ensure quiet cards still expose an AI prompt when they only have navigate/analyze.
        if cid in _CARD_ACTIONS and not any(a.get("type") == "prompt" for a in raw_actions):
            prompt_bank = {
                "risk": {
                    "type": "prompt",
                    "labelDe": "KI: Compliance-Lage",
                    "labelEn": "AI: Compliance status",
                    "labelAr": "AI: وضع الامتثال",
                    "promptDe": "Prüfe Compliance: abgelaufene Dokumente, Sperren und Risiko-Score. Top-3 Maßnahmen.",
                    "promptEn": "Check compliance: expired docs, locks and risk score. Top 3 actions.",
                    "promptAr": "افحص الامتثال: الوثائق المنتهية والإيقافات ودرجة المخاطر. أهم 3 إجراءات.",
                },
                "leave": {
                    "type": "prompt",
                    "labelDe": "KI: Urlaubsanträge",
                    "labelEn": "AI: Leave requests",
                    "labelAr": "AI: طلبات الإجازة",
                    "promptDe": "Welche Urlaubs- oder Krankmeldungen sind offen und was empfiehlst du?",
                    "promptEn": "Which leave requests are open and what do you recommend?",
                    "promptAr": "ما طلبات الإجازة المفتوحة وما توصيتك؟",
                },
            }
            if cid in prompt_bank:
                raw_actions.append(prompt_bank[cid])
        actions: list[dict[str, Any]] = []
        for a in raw_actions:
            act: dict[str, Any] = {"type": a["type"]}
            if a["type"] == "navigate":
                act["url"] = a["url"]
                act["label"] = _apply_sector_text(_localized(a, lang, "label"), workers=workers, site=site, lang=lang)
            elif a["type"] == "analyze":
                act["topic"] = a.get("topic", "operations")
                act["label"] = _apply_sector_text(_localized(a, lang, "label"), workers=workers, site=site, lang=lang)
            elif a["type"] == "prompt":
                act["prompt"] = _apply_sector_text(_localized(a, lang, "prompt"), workers=workers, site=site, lang=lang)
                short = _apply_sector_text(_localized(a, lang, "label"), workers=workers, site=site, lang=lang)
                act["label"] = short or (act["prompt"][:42] + ("…" if len(act["prompt"]) > 42 else ""))
            actions.append(act)
        if actions:
            card["actions"] = actions

    next_actions: list[dict[str, Any]] = []
    for rec in dash.get("recommendations") or []:
        spec = _RECOMMENDATIONS.get(rec)
        if not spec:
            continue
        item: dict[str, Any] = {
            "id": rec,
            "type": spec["type"],
            "label": _apply_sector_text(_localized(spec, lang, "label"), workers=workers, site=site, lang=lang),
        }
        if spec["type"] == "navigate":
            item["url"] = spec.get("url", "/ai-command-center.html")
        elif spec["type"] == "analyze":
            item["topic"] = spec.get("topic", "operations")
        elif spec["type"] == "prompt":
            item["prompt"] = _apply_sector_text(_localized(spec, lang, "prompt"), workers=workers, site=site, lang=lang)
        next_actions.append(item)

    if not next_actions and int((dash.get("snapshot") or {}).get("openSecurityFindings") or 0) > 0:
        next_actions.append(
            {
                "id": "default_security",
                "type": "analyze",
                "topic": "security",
                "label": _apply_sector_text(
                    _localized(_RECOMMENDATIONS["review_security_findings"], lang, "label"),
                    workers=workers,
                    site=site,
                    lang=lang,
                ),
            }
        )

    # Always offer a few working AI prompts — even when metrics are zero.
    if not next_actions:
        next_actions.extend(
            [
                {
                    "id": "default_onsite",
                    "type": "prompt",
                    "label": _apply_sector_text(
                        _localized(_CARD_ACTIONS["onsite"][2], lang, "label") or "KI: Wer ist vor Ort?",
                        workers=workers,
                        site=site,
                        lang=lang,
                    ),
                    "prompt": _apply_sector_text(
                        _localized(_CARD_ACTIONS["onsite"][2], lang, "prompt"),
                        workers=workers,
                        site=site,
                        lang=lang,
                    ),
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
                {
                    "id": "default_compliance",
                    "type": "analyze",
                    "topic": "compliance",
                    "label": _localized(_CARD_ACTIONS["risk"][0], lang, "label"),
                },
                {
                    "id": "default_workers",
                    "type": "navigate",
                    "url": "/admin-v2/index.html?tab=workers",
                    "label": _apply_sector_text(
                        _localized(_CARD_ACTIONS["risk"][1], lang, "label"),
                        workers=workers,
                        site=site,
                        lang=lang,
                    ),
                },
            ]
        )

    dash["nextActions"] = next_actions[:6]
    dash["playbookUrl"] = f"/ai-command-center.html?{qs}"
    dash["opsUrl"] = f"/ops-command-center.html?{qs}"
    return dash
