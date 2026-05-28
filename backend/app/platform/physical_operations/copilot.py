"""AI Operations Copilot — auto context from live operations data."""
from __future__ import annotations

from typing import Any

from .command_center import build_command_center
from .digital_twin import build_digital_twin
from .emergency import build_emergency_status
from .identity_hub import build_identity_hub
from .reputation import build_reputation_leaderboard
from .security_engine import analyze_security
from .site_intelligence import build_site_intelligence
from ._common import count_on_site, list_on_site_workers, today_prefix


def build_copilot_context(db, company_id: str, role: str = "company-admin") -> dict[str, Any]:
    today = today_prefix()
    active_emergency = None
    try:
        row = db.execute(
            "SELECT id FROM emergency_events WHERE company_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (company_id,),
        ).fetchone()
        if row:
            active_emergency = build_emergency_status(db, row["id"], company_id)
    except Exception:
        pass
    return {
        "date": today,
        "workersOnSite": count_on_site(db, company_id, today),
        "onSiteWorkers": list_on_site_workers(db, company_id, today)[:30],
        "siteIntelligence": build_site_intelligence(db, company_id),
        "security": analyze_security(db, company_id, persist=False),
        "digitalTwinSummary": build_digital_twin(db, company_id).get("summary"),
        "reputationTop5": build_reputation_leaderboard(db, company_id, limit=20)["workers"][:5],
        "activeEmergency": active_emergency,
        "identity": build_identity_hub(db, company_id),
        "commandCenter": build_command_center(db, company_id=company_id, role=role),
    }


def copilot_query(db, company_id: str, question: str, role: str = "company-admin") -> dict[str, Any]:
    from backend.app.platform.ai.assistant import is_ai_configured, natural_language_query

    ctx = build_copilot_context(db, company_id, role)
    if not is_ai_configured():
        return {
            "configured": False,
            "hint": "Set OPENAI_API_KEY to enable natural language answers.",
            "context": ctx,
            "deterministicAnswers": _deterministic_qa(ctx, question),
        }
    result = natural_language_query(company_id, question, ctx)
    result["contextSummary"] = {
        "workersOnSite": ctx["workersOnSite"],
        "openSecurityFindings": len(ctx.get("security", {}).get("findings", [])),
        "operationalIssues": len(ctx.get("siteIntelligence", {}).get("operationalIssues", [])),
    }
    return result


def _deterministic_qa(ctx: dict, question: str) -> dict[str, Any]:
    q = question.lower()
    if "inside" in q or "on site" in q or "موقع" in q or "داخل" in q:
        return {"answer": f"{ctx['workersOnSite']} workers currently on site.", "source": "live_access_logs"}
    if "late" in q or "متأخر" in q:
        issues = ctx.get("siteIntelligence", {}).get("operationalIssues", [])
        return {"answer": issues or "No critical late-shift issues in rules.", "source": "site_intelligence"}
    if "compliance" in q or "مخاطر" in q or "risk" in q:
        sec = ctx.get("security", {})
        return {
            "answer": f"{len(sec.get('findings', []))} security findings; check open alerts.",
            "source": "security_engine",
        }
    if "emergency" in q or "طوارئ" in q:
        em = ctx.get("activeEmergency")
        if em:
            return {"answer": em.get("summary"), "source": "emergency"}
        return {"answer": "No active emergency.", "source": "emergency"}
    return {"answer": None, "source": "needs_llm"}
