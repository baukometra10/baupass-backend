"""Compact operations context and prompt helpers for the AI assistant."""
from __future__ import annotations

import time
from typing import Any

_COMPACT_CTX_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_COMPACT_CTX_TTL_SEC = 30.0


def invalidate_compact_context_cache(company_id: str | None = None) -> None:
    if not company_id:
        _COMPACT_CTX_CACHE.clear()
        return
    prefix = f"{company_id}:"
    for key in list(_COMPACT_CTX_CACHE):
        if key.startswith(prefix):
            _COMPACT_CTX_CACHE.pop(key, None)


def build_compact_context(db, company_id: str, role: str = "company-admin", *, lang: str = "de") -> dict[str, Any]:
    from backend.app.platform.ai.intelligence import operational_insights
    from backend.app.platform.physical_operations.copilot import build_copilot_context

    cid = str(company_id or "").strip()
    lang_code = (lang or "de")[:2]
    cache_key = f"{cid}:{role}:{lang_code}"
    now = time.monotonic()
    cached = _COMPACT_CTX_CACHE.get(cache_key)
    if cached and now - cached[0] < _COMPACT_CTX_TTL_SEC:
        return cached[1]

    full = build_copilot_context(db, company_id, role)
    workers = full.get("onSiteWorkers") or []
    sec = full.get("security") or {}
    findings = sec.get("findings") or []
    site = full.get("siteIntelligence") or {}
    em = full.get("activeEmergency")
    identity = (full.get("identity") or {}).get("summary") or {}
    pending_leave = 0
    try:
        row = db.execute(
            """
            SELECT COUNT(*) AS c FROM leave_requests lr
            JOIN workers w ON w.id = lr.worker_id
            WHERE w.company_id = ? AND lr.status IN ('pending', 'ausstehend')
            """,
            (company_id,),
        ).fetchone()
        pending_leave = int((row["c"] if row else 0) or 0)
    except Exception:
        pass

    company_row = db.execute(
        "SELECT name FROM companies WHERE id = ? AND deleted_at IS NULL",
        (company_id,),
    ).fetchone()
    company_name = (company_row["name"] if company_row else "") or company_id

    sector_terms: dict[str, str] = {}
    try:
        from backend.app.platform.sector.catalog import sector_terms_for_company

        sector_terms = sector_terms_for_company(db, company_id, lang=lang_code)
    except Exception:
        sector_terms = {}

    result = {
        "companyId": company_id,
        "companyName": company_name,
        "operatingSector": sector_terms.get("_sector") or "construction",
        "sectorLabel": sector_terms.get("_sectorLabel") or "",
        "sectorTerms": sector_terms,
        "date": full.get("date"),
        "workersOnSite": full.get("workersOnSite", 0),
        "onSiteNames": [
            f"{w.get('first_name', '')} {w.get('last_name', '')}".strip()
            for w in workers[:25]
            if f"{w.get('first_name', '')} {w.get('last_name', '')}".strip()
        ],
        "operationalIssues": (site.get("operationalIssues") or [])[:10],
        "busiestGates": (site.get("busiestGates") or [])[:5],
        "peakHour": site.get("peakHour"),
        "security": {
            "openFindings": len(findings),
            "openAlerts": len(sec.get("openAlerts") or []),
            "topFindings": [
                {
                    "type": f.get("alert_type"),
                    "severity": f.get("severity"),
                    "title": f.get("title"),
                    "workerId": f.get("worker_id"),
                }
                for f in findings[:12]
            ],
        },
        "reputationTop5": full.get("reputationTop5") or [],
        "digitalTwinSummary": full.get("digitalTwinSummary"),
        "emergency": (
            {
                "active": True,
                "summary": em.get("summary"),
                "missing": len(em.get("missing") or []),
                "onSite": len(em.get("onSite") or []),
            }
            if em
            else {"active": False}
        ),
        "identity": identity,
        "intelligence": operational_insights(db, company_id),
        "pendingLeave": pending_leave,
    }
    _COMPACT_CTX_CACHE[cache_key] = (now, result)
    if len(_COMPACT_CTX_CACHE) > 64:
        oldest = sorted(_COMPACT_CTX_CACHE.items(), key=lambda kv: kv[1][0])[:16]
        for key, _ in oldest:
            _COMPACT_CTX_CACHE.pop(key, None)
    return result


def infer_context_sources(ctx: dict[str, Any]) -> list[str]:
    sources = ["access_logs", "site_intelligence"]
    sec = ctx.get("security") or {}
    if int(sec.get("openFindings") or 0) > 0 or int(sec.get("openAlerts") or 0) > 0:
        sources.append("security_engine")
    if (ctx.get("emergency") or {}).get("active"):
        sources.append("emergency")
    intel = ctx.get("intelligence") or {}
    if intel.get("attendance", {}).get("at_risk"):
        sources.append("predictive_attendance")
    if intel.get("fraud", {}).get("signals"):
        sources.append("fraud_detection")
    if intel.get("risk", {}).get("level") in ("medium", "high"):
        sources.append("workforce_risk")
    return sources


def format_live_context_block(ctx: dict[str, Any], *, lang: str = "de") -> str:
    """Human-readable context block for LLM system prompts."""
    lang = (lang or "de")[:2]
    name = str(ctx.get("companyName") or ctx.get("companyId") or "—")
    on_site = int(ctx.get("workersOnSite") or 0)
    names = [n for n in (ctx.get("onSiteNames") or []) if n][:12]
    sec = ctx.get("security") or {}
    sec_n = int(sec.get("openFindings") or 0)
    alerts_n = int(sec.get("openAlerts") or 0)
    em = ctx.get("emergency") or {}
    pending_leave = int(ctx.get("pendingLeave") or 0)
    issues = ctx.get("operationalIssues") or []
    terms = ctx.get("sectorTerms") or {}
    site = str(terms.get("termSite") or ("site" if lang == "en" else "موقع" if lang == "ar" else "Standort")).strip()
    workers = str(terms.get("termWorkers") or ("workers" if lang == "en" else "عمال" if lang == "ar" else "Mitarbeiter")).strip()
    gate = str(terms.get("termGate") or ("gate" if lang == "en" else "بوابة" if lang == "ar" else "Tor")).strip()
    sector_label = str(ctx.get("sectorLabel") or terms.get("_sectorLabel") or "").strip()

    if lang == "en":
        lines = [
            f"Company: {name}",
            f"Operating sector: {sector_label or ctx.get('operatingSector') or 'construction'}",
            f"Date: {ctx.get('date') or '—'}",
            f"At {site} now: {on_site} {workers}",
        ]
        if names:
            lines.append(f"Names at {site}: " + ", ".join(names))
        if sec_n or alerts_n:
            lines.append(f"Open security findings: {sec_n}, alerts: {alerts_n}")
        if em.get("active"):
            lines.append(f"Active emergency: {em.get('summary') or 'yes'}")
        if pending_leave:
            lines.append(f"Pending leave requests: {pending_leave}")
        if issues:
            lines.append(f"{site} notes: " + "; ".join(str(i) for i in issues[:5]))
        lines.append(f"Use sector vocabulary: {workers}, {site}, {gate}.")
        return "\n".join(lines)

    if lang == "ar":
        lines = [
            f"الشركة: {name}",
            f"القطاع: {sector_label or ctx.get('operatingSector') or 'construction'}",
            f"التاريخ: {ctx.get('date') or '—'}",
            f"في {site} الآن: {on_site} {workers}",
        ]
        if names:
            lines.append(f"أسماء في {site}: " + "، ".join(names))
        lines.append(f"استخدم مصطلحات القطاع: {workers}، {site}، {gate}.")
        return "\n".join(lines)

    lines = [
        f"Firma: {name}",
        f"Betriebssektor: {sector_label or ctx.get('operatingSector') or 'construction'}",
        f"Datum: {ctx.get('date') or '—'}",
        f"Gerade am Standort ({site}): {on_site} {workers}",
    ]
    if names:
        lines.append(f"Namen vor Ort: " + ", ".join(names))
    if sec_n or alerts_n:
        lines.append(f"Offene Sicherheitsbefunde: {sec_n}, Alerts: {alerts_n}")
    if em.get("active"):
        lines.append(f"Aktiver Notfall: {em.get('summary') or 'ja'}")
    if pending_leave:
        lines.append(f"Offene Urlaubsanträge: {pending_leave}")
    if issues:
        lines.append(f"Hinweise ({site}): " + "; ".join(str(i) for i in issues[:5]))
    intel = ctx.get("intelligence") or {}
    risk = (intel.get("risk") or {}).get("level")
    if risk:
        lines.append(f"Workforce-Risiko: {risk}")
    lines.append(f"Verwende die Fachsprache des Sektors: {workers}, {site}, {gate}.")
    return "\n".join(lines)


def suggested_prompts(ctx: dict[str, Any], lang: str = "de") -> list[dict[str, str]]:
    on_site = int(ctx.get("workersOnSite") or 0)
    sec_n = int((ctx.get("security") or {}).get("openFindings") or 0)
    issues = ctx.get("operationalIssues") or []
    em = (ctx.get("emergency") or {}).get("active")
    at_risk = len((ctx.get("intelligence") or {}).get("attendance", {}).get("at_risk") or [])
    terms = ctx.get("sectorTerms") or {}
    site = str(terms.get("termSite") or ("site" if lang.startswith("en") else "موقع" if lang.startswith("ar") else "Standort")).strip()
    workers = str(terms.get("termWorkers") or ("workers" if lang.startswith("en") else "عمال" if lang.startswith("ar") else "Mitarbeiter")).strip()
    gate = str(terms.get("termGate") or ("gates" if lang.startswith("en") else "بوابات" if lang.startswith("ar") else "Tore")).strip()

    bank = {
        "de": [
            ("briefing", f"Erstelle ein Tagesbriefing für {site}."),
            ("onsite", f"Wer ist gerade am Standort ({site})? ({on_site} laut System)"),
            ("security", f"Welche Sicherheitsrisiken sind offen? ({sec_n} Befunde)"),
            ("gates", f"Welche {gate} sind heute am stärksten genutzt?"),
            ("attendance", f"Welche {workers} haben erhöhtes Ausfallrisiko? ({at_risk} Hinweise)"),
            ("compliance", "Gibt es Compliance- oder Dokumentenrisiken?"),
            ("emergency", "Gibt es einen aktiven Notfall — was ist der Status?"),
            ("actions", "Welche 3 Maßnahmen sollte ich heute priorisieren?"),
        ],
        "en": [
            ("briefing", f"Create today's operations briefing for {site}."),
            ("onsite", f"Who is at {site} right now? ({on_site} in system)"),
            ("security", f"What security risks are open? ({sec_n} findings)"),
            ("gates", f"Which {gate} had the most traffic today?"),
            ("attendance", f"Which {workers} have elevated no-show risk? ({at_risk} signals)"),
            ("compliance", "Any compliance or document expiry risks?"),
            ("emergency", "Is there an active emergency — what is the status?"),
            ("actions", "What are the top 3 actions I should prioritize today?"),
        ],
        "ar": [
            ("briefing", f"أنشئ ملخص عمليات اليوم لـ {site}."),
            ("onsite", f"من موجود في {site} الآن؟ ({on_site} في النظام)"),
            ("security", f"ما مخاطر الأمن المفتوحة؟ ({sec_n} نتائج)"),
            ("gates", f"أي {gate} الأكثر استخداماً اليوم؟"),
            ("attendance", f"أي {workers} معرضون لغياب مرتفع؟ ({at_risk} إشارات)"),
            ("compliance", "هل توجد مخاطر امتثال أو وثائق منتهية؟"),
            ("emergency", "هل هناك طوارئ نشطة — ما الحالة؟"),
            ("actions", "ما أهم 3 إجراءات يجب أن أبدأ بها اليوم؟"),
        ],
    }
    items = list(bank.get(lang[:2], bank["de"]))
    out: list[dict[str, str]] = []
    for key, text in items:
        if key == "emergency" and not em:
            continue
        if key == "attendance" and at_risk == 0:
            continue
        if key == "security" and sec_n == 0 and not issues:
            continue
        out.append({"id": key, "text": text})
    return out[:6]


def deterministic_briefing(ctx: dict[str, Any], lang: str = "de") -> str:
    on_site = int(ctx.get("workersOnSite") or 0)
    sec_n = int((ctx.get("security") or {}).get("openFindings") or 0)
    issues = ctx.get("operationalIssues") or []
    em = ctx.get("emergency") or {}
    intel = ctx.get("intelligence") or {}
    risk = intel.get("risk") or {}
    prod = intel.get("productivity") or {}
    at_risk = intel.get("attendance", {}).get("at_risk") or []
    terms = ctx.get("sectorTerms") or {}
    site = str(terms.get("termSite") or ("site" if lang.startswith("en") else "موقع" if lang.startswith("ar") else "Standort")).strip()
    workers = str(terms.get("termWorkers") or ("workers" if lang.startswith("en") else "عمال" if lang.startswith("ar") else "Mitarbeiter")).strip()

    if lang.startswith("en"):
        lines = [
            f"**Operations briefing ({ctx.get('date', '')})**",
            f"- At {site} now: **{on_site}** {workers}",
            f"- Check-ins / check-outs today: {prod.get('checkins', 0)} / {prod.get('checkouts', 0)}",
            f"- Security findings: **{sec_n}**",
            f"- Workforce risk level: **{risk.get('level', 'low')}** (score {risk.get('risk_score', 0)})",
        ]
        if em.get("active"):
            lines.append(f"- **Active emergency:** {em.get('summary', 'yes')}")
        if issues:
            lines.append(f"- {site} issues: {len(issues)} (e.g. {issues[0].get('message', '')[:80]})")
        if at_risk:
            lines.append(f"- Attendance risk: {len(at_risk)} {workers} flagged")
        lines.append("- Use AI chat for detailed follow-up questions.")
        return "\n".join(lines)

    if lang.startswith("ar"):
        lines = [
            f"**ملخص العمليات ({ctx.get('date', '')})**",
            f"- في {site} الآن: **{on_site}** {workers}",
            f"- دخول / خروج اليوم: {prod.get('checkins', 0)} / {prod.get('checkouts', 0)}",
            f"- نتائج الأمن: **{sec_n}**",
            f"- مستوى المخاطر: **{risk.get('level', 'low')}**",
        ]
        if em.get("active"):
            lines.append(f"- **طوارئ نشطة:** {em.get('summary', '')}")
        return "\n".join(lines)

    lines = [
        f"**Tagesbriefing ({ctx.get('date', '')})**",
        f"- Aktuell am Standort ({site}): **{on_site}** {workers}",
        f"- Check-ins / Check-outs heute: {prod.get('checkins', 0)} / {prod.get('checkouts', 0)}",
        f"- Sicherheitsbefunde: **{sec_n}**",
        f"- Workforce-Risiko: **{risk.get('level', 'low')}** (Score {risk.get('risk_score', 0)})",
    ]
    if em.get("active"):
        lines.append(f"- **Aktiver Notfall:** {em.get('summary', 'ja')}")
    if issues:
        lines.append(f"- Hinweise ({site}): {len(issues)} (z. B. {issues[0].get('message', '')[:80]})")
    if at_risk:
        lines.append(f"- Anwesenheitsrisiko: {len(at_risk)} {workers} markiert")
    lines.append("- Für Details: gezielte Fragen im KI-Chat stellen.")
    return "\n".join(lines)


def format_analysis_data_block(ctx: dict[str, Any], topic: str, *, lang: str = "de") -> str:
    """Rich pre-loaded data for one-shot analysis (no OpenAI tool rounds)."""
    import json

    topic = (topic or "operations").strip().lower()
    intel = ctx.get("intelligence") or {}
    sec = ctx.get("security") or {}
    payload: dict[str, Any] = {
        "analysisTopic": topic,
        "companyName": ctx.get("companyName"),
        "date": ctx.get("date"),
        "workersOnSite": ctx.get("workersOnSite"),
        "onSiteNames": (ctx.get("onSiteNames") or [])[:20],
        "operationalIssues": (ctx.get("operationalIssues") or [])[:8],
        "busiestGates": (ctx.get("busiestGates") or [])[:5],
        "emergency": ctx.get("emergency"),
        "intelligence": intel,
        "securityFindings": (sec.get("topFindings") or [])[:15],
        "openSecurityFindings": sec.get("openFindings"),
        "openSecurityAlerts": sec.get("openAlerts"),
        "pendingLeave": ctx.get("pendingLeave"),
    }
    if topic in {"security", "operations", "executive"}:
        payload["fraudSignals"] = (intel.get("fraud") or {}).get("signals") or []
    if topic in {"compliance", "executive"}:
        payload["workforceRisk"] = intel.get("risk") or {}
    if topic in {"attendance", "hr", "executive"}:
        payload["attendanceRisk"] = (intel.get("attendance") or {}).get("at_risk") or []

    blob = json.dumps(payload, ensure_ascii=False)[:12000]
    if lang == "en":
        return (
            f"Deep analysis topic: {topic}. Use ONLY this live JSON — do not invent data.\n"
            f"Be concise: max 8 bullets + 3 prioritized actions.\n{blob}"
        )
    if lang == "ar":
        return (
            f"موضوع التحليل: {topic}. استخدم JSON فقط — لا تخترع بيانات.\n"
            f"كن مختصراً: 8 نقاط كحد أقصى + 3 إجراءات.\n{blob}"
        )
    return (
        f"Tiefenanalyse-Thema: {topic}. Nutze NUR dieses Live-JSON — keine erfundenen Daten.\n"
        f"Kurz halten: max. 8 Bulletpoints + 3 priorisierte Maßnahmen.\n{blob}"
    )
