"""AI insights dashboard — structured cards for Command Center UI."""
from __future__ import annotations

from typing import Any

from backend.app.platform.ai.context_builder import build_compact_context, infer_context_sources
from backend.app.platform.ai.intelligence import operational_insights


def build_insights_dashboard(db, company_id: str, role: str = "company-admin") -> dict[str, Any]:
    ctx = build_compact_context(db, company_id, role)
    intel = ctx.get("intelligence") or operational_insights(db, company_id)
    forecast = {}
    try:
        from backend.app.platform.predictions.engine import build_tomorrow_forecast

        forecast = build_tomorrow_forecast(db, company_id)
    except Exception:
        pass
    sec = ctx.get("security") or {}
    em = ctx.get("emergency") or {}
    risk = intel.get("risk") or {}
    prod = intel.get("productivity") or {}
    at_risk = intel.get("attendance", {}).get("at_risk") or []
    fraud = intel.get("fraud", {}).get("signals") or []

    cards: list[dict[str, Any]] = [
        {
            "id": "onsite",
            "severity": "info",
            "titleKey": "onsite",
            "value": ctx.get("workersOnSite", 0),
            "detail": ", ".join((ctx.get("onSiteNames") or [])[:5])
            or ("Niemand eingecheckt — Lage prüfen" if not ctx.get("workersOnSite") else ""),
        },
        {
            "id": "security",
            "severity": "high" if int(sec.get("openFindings") or 0) > 3 else "medium" if sec.get("openFindings") else "low",
            "titleKey": "security",
            "value": int(sec.get("openFindings") or 0),
            "detail": (
                (sec.get("topFindings") or [{}])[0].get("title", "")
                if sec.get("topFindings")
                else ("Keine offenen Befunde — Kurzcheck möglich" if not sec.get("openFindings") else "")
            ),
        },
        {
            "id": "risk",
            "severity": risk.get("level", "low"),
            "titleKey": "workforceRisk",
            "value": risk.get("risk_score", 0),
            "detail": (
                f"{risk.get('expired_documents', 0)} docs · {risk.get('locked_workers', 0)} locked"
                if int(risk.get("expired_documents") or 0) or int(risk.get("locked_workers") or 0) or int(risk.get("risk_score") or 0)
                else "Keine abgelaufenen Dokumente · keine Sperren"
            ),
        },
        {
            "id": "attendance",
            "severity": "medium" if at_risk else "low",
            "titleKey": "attendanceRisk",
            "value": len(at_risk),
            "detail": at_risk[0].get("name", "") if at_risk else "Kein Ausfallrisiko erkannt — Analyse starten",
        },
        {
            "id": "fraud",
            "severity": "high" if fraud else "low",
            "titleKey": "fraud",
            "value": len(fraud),
            "detail": fraud[0].get("type", "") if fraud else "Keine Betrugssignale — optional prüfen",
        },
        {
            "id": "productivity",
            "severity": "info",
            "titleKey": "productivity",
            "value": f"{prod.get('checkins', 0)}/{prod.get('checkouts', 0)}",
            "detail": ctx.get("peakHour") or ("Noch keine Stempel heute" if not prod.get("checkins") else ""),
        },
    ]

    if forecast.get("expectedAbsent", 0) > 0:
        cards.insert(
            0,
            {
                "id": "tomorrow",
                "severity": "medium" if forecast.get("expectedAbsent", 0) < 4 else "high",
                "titleKey": "tomorrowForecast",
                "value": forecast.get("expectedOnSite", 0),
                "detail": forecast.get("summary", "")[:120],
            },
        )

    if em.get("active"):
        cards.insert(
            0,
            {
                "id": "emergency",
                "severity": "critical",
                "titleKey": "emergency",
                "value": 1,
                "detail": em.get("summary", ""),
            },
        )

    pending_leave = int(ctx.get("pendingLeave") or 0)
    if pending_leave > 0:
        cards.insert(
            0,
            {
                "id": "leave",
                "severity": "medium" if pending_leave < 4 else "high",
                "titleKey": "pendingLeave",
                "value": pending_leave,
                "detail": "Offene Urlaubs- und Krankmeldungen",
                "actions": [
                    {
                        "type": "navigate",
                        "label": "Anträge öffnen",
                        "url": "/admin-v2/index.html?tab=inbox",
                    }
                ],
            },
        )

    issues = ctx.get("operationalIssues") or []
    recommendations: list[str] = []
    if int(sec.get("openFindings") or 0) > 0:
        recommendations.append("review_security_findings")
    if at_risk:
        recommendations.append("contact_at_risk_workers")
    if int(forecast.get("expectedAbsent") or 0) >= 3:
        recommendations.append("plan_tomorrow_staffing")
    if issues:
        recommendations.append("investigate_low_activity_sites")
    if em.get("active"):
        recommendations.append("manage_active_emergency")
    if int(risk.get("expired_documents") or 0) > 0:
        recommendations.append("renew_expired_documents")

    return {
        "companyId": company_id,
        "date": ctx.get("date"),
        "cards": cards,
        "operationalIssues": issues[:8],
        "recommendations": recommendations,
        "sources": infer_context_sources(ctx),
        "tomorrowForecast": forecast,
        "snapshot": {
            "workersOnSite": ctx.get("workersOnSite"),
            "openSecurityFindings": sec.get("openFindings"),
            "riskLevel": risk.get("level"),
        },
    }
