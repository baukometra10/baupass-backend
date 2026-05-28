"""Compact operations context and prompt helpers for the AI assistant."""
from __future__ import annotations

from typing import Any


def build_compact_context(db, company_id: str, role: str = "company-admin") -> dict[str, Any]:
    from backend.app.platform.ai.intelligence import operational_insights
    from backend.app.platform.physical_operations.copilot import build_copilot_context

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

    return {
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


def suggested_prompts(ctx: dict[str, Any], lang: str = "de") -> list[dict[str, str]]:
    on_site = int(ctx.get("workersOnSite") or 0)
    sec_n = int((ctx.get("security") or {}).get("openFindings") or 0)
    issues = ctx.get("operationalIssues") or []
    em = (ctx.get("emergency") or {}).get("active")
    at_risk = len((ctx.get("intelligence") or {}).get("attendance", {}).get("at_risk") or [])

    bank = {
        "de": [
            ("briefing", "Erstelle ein Tagesbriefing für die Baustelle."),
            ("onsite", f"Wer ist gerade auf der Baustelle? ({on_site} laut System)"),
            ("security", f"Welche Sicherheitsrisiken sind offen? ({sec_n} Befunde)"),
            ("gates", "Welche Tore sind heute am stärksten genutzt?"),
            ("attendance", f"Wer hat ein erhöhtes Ausfallrisiko? ({at_risk} Hinweise)"),
            ("compliance", "Gibt es Compliance- oder Dokumentenrisiken?"),
            ("emergency", "Gibt es einen aktiven Notfall — was ist der Status?"),
            ("actions", "Welche 3 Maßnahmen sollte ich heute priorisieren?"),
        ],
        "en": [
            ("briefing", "Create today's site operations briefing."),
            ("onsite", f"Who is on site right now? ({on_site} in system)"),
            ("security", f"What security risks are open? ({sec_n} findings)"),
            ("gates", "Which gates had the most traffic today?"),
            ("attendance", f"Who has elevated no-show risk? ({at_risk} signals)"),
            ("compliance", "Any compliance or document expiry risks?"),
            ("emergency", "Is there an active emergency — what is the status?"),
            ("actions", "What are the top 3 actions I should prioritize today?"),
        ],
        "ar": [
            ("briefing", "أنشئ ملخص عمليات اليوم للموقع."),
            ("onsite", f"من موجود على الموقع الآن؟ ({on_site} في النظام)"),
            ("security", f"ما مخاطر الأمن المفتوحة؟ ({sec_n} نتائج)"),
            ("gates", "أي البوابات الأكثر استخداماً اليوم؟"),
            ("attendance", f"من معرض لغياب مرتفع؟ ({at_risk} إشارات)"),
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

    if lang.startswith("en"):
        lines = [
            f"**Operations briefing ({ctx.get('date', '')})**",
            f"- On site now: **{on_site}** workers",
            f"- Check-ins / check-outs today: {prod.get('checkins', 0)} / {prod.get('checkouts', 0)}",
            f"- Security findings: **{sec_n}**",
            f"- Workforce risk level: **{risk.get('level', 'low')}** (score {risk.get('risk_score', 0)})",
        ]
        if em.get("active"):
            lines.append(f"- **Active emergency:** {em.get('summary', 'yes')}")
        if issues:
            lines.append(f"- Site issues: {len(issues)} (e.g. {issues[0].get('message', '')[:80]})")
        if at_risk:
            lines.append(f"- Attendance risk: {len(at_risk)} workers flagged")
        lines.append("- Use AI chat for detailed follow-up questions.")
        return "\n".join(lines)

    if lang.startswith("ar"):
        lines = [
            f"**ملخص العمليات ({ctx.get('date', '')})**",
            f"- على الموقع الآن: **{on_site}**",
            f"- دخول / خروج اليوم: {prod.get('checkins', 0)} / {prod.get('checkouts', 0)}",
            f"- نتائج الأمن: **{sec_n}**",
            f"- مستوى المخاطر: **{risk.get('level', 'low')}**",
        ]
        if em.get("active"):
            lines.append(f"- **طوارئ نشطة:** {em.get('summary', '')}")
        return "\n".join(lines)

    lines = [
        f"**Tagesbriefing ({ctx.get('date', '')})**",
        f"- Aktuell auf der Baustelle: **{on_site}** Mitarbeiter",
        f"- Check-ins / Check-outs heute: {prod.get('checkins', 0)} / {prod.get('checkouts', 0)}",
        f"- Sicherheitsbefunde: **{sec_n}**",
        f"- Workforce-Risiko: **{risk.get('level', 'low')}** (Score {risk.get('risk_score', 0)})",
    ]
    if em.get("active"):
        lines.append(f"- **Aktiver Notfall:** {em.get('summary', 'ja')}")
    if issues:
        lines.append(f"- Standort-Hinweise: {len(issues)} (z. B. {issues[0].get('message', '')[:80]})")
    if at_risk:
        lines.append(f"- Anwesenheitsrisiko: {len(at_risk)} Mitarbeiter markiert")
    lines.append("- Für Details: gezielte Fragen im KI-Chat stellen.")
    return "\n".join(lines)
