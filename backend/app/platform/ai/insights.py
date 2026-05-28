"""AI insights dashboard — structured cards for Command Center UI."""
from __future__ import annotations

from typing import Any

from backend.app.platform.ai.context_builder import build_compact_context, infer_context_sources
from backend.app.platform.ai.intelligence import operational_insights


def build_insights_dashboard(db, company_id: str, role: str = "company-admin") -> dict[str, Any]:
    ctx = build_compact_context(db, company_id, role)
    intel = ctx.get("intelligence") or operational_insights(db, company_id)
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
            "detail": ", ".join((ctx.get("onSiteNames") or [])[:5]),
        },
        {
            "id": "security",
            "severity": "high" if int(sec.get("openFindings") or 0) > 3 else "medium" if sec.get("openFindings") else "low",
            "titleKey": "security",
            "value": int(sec.get("openFindings") or 0),
            "detail": (sec.get("topFindings") or [{}])[0].get("title", "") if sec.get("topFindings") else "",
        },
        {
            "id": "risk",
            "severity": risk.get("level", "low"),
            "titleKey": "workforceRisk",
            "value": risk.get("risk_score", 0),
            "detail": f"{risk.get('expired_documents', 0)} docs · {risk.get('locked_workers', 0)} locked",
        },
        {
            "id": "attendance",
            "severity": "medium" if at_risk else "low",
            "titleKey": "attendanceRisk",
            "value": len(at_risk),
            "detail": at_risk[0].get("name", "") if at_risk else "",
        },
        {
            "id": "fraud",
            "severity": "high" if fraud else "low",
            "titleKey": "fraud",
            "value": len(fraud),
            "detail": fraud[0].get("type", "") if fraud else "",
        },
        {
            "id": "productivity",
            "severity": "info",
            "titleKey": "productivity",
            "value": f"{prod.get('checkins', 0)}/{prod.get('checkouts', 0)}",
            "detail": ctx.get("peakHour") or "",
        },
    ]

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

    issues = ctx.get("operationalIssues") or []
    recommendations: list[str] = []
    if int(sec.get("openFindings") or 0) > 0:
        recommendations.append("review_security_findings")
    if at_risk:
        recommendations.append("contact_at_risk_workers")
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
        "snapshot": {
            "workersOnSite": ctx.get("workersOnSite"),
            "openSecurityFindings": sec.get("openFindings"),
            "riskLevel": risk.get("level"),
        },
    }
