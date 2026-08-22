"""AI Operations Copilot — auto context from live operations data."""
from __future__ import annotations

import logging
from typing import Any

from .command_center import build_command_center
from .digital_twin import build_digital_twin
from .emergency import build_emergency_status
from .identity_hub import build_identity_hub
from .reputation import build_reputation_leaderboard
from .security_engine import analyze_security
from .site_intelligence import build_site_intelligence
from ._common import count_on_site, list_on_site_workers, today_prefix


def _daily_brief_for_copilot(db, company_id: str) -> dict[str, Any]:
    """Slim daily-brief KPIs for Copilot (attendance / security / chat / hr)."""
    try:
        from .daily_brief import build_daily_ops_brief

        brief = build_daily_ops_brief(db, company_id) or {}
    except Exception:
        return {}
    att = brief.get("attendance") or {}
    sec = brief.get("security") or {}
    chat = brief.get("chat") or {}
    hr = brief.get("hr") or {}
    return {
        "attendance": {
            "onSite": int(att.get("onSite") or 0),
            "checkInsToday": int(att.get("checkInsToday") or 0),
            "lateToday": int(att.get("lateToday") or 0),
            "outsideHoursAttemptsToday": int(att.get("outsideHoursAttemptsToday") or 0),
            "expectedToday": int(att.get("expectedToday") or 0),
            "missingExpected": int(att.get("missingExpected") or 0),
            "lateWorkers": list(att.get("lateWorkers") or [])[:6],
            "missingWorkers": list(att.get("missingWorkers") or [])[:6],
            "workWindow": att.get("workWindow") or {},
        },
        "security": {
            "openCameraEscalations": int(sec.get("openCameraEscalations") or 0),
            "openSecurityAlerts": int(sec.get("openSecurityAlerts") or 0),
            "totalOpen": int(sec.get("totalOpen") or 0),
        },
        "chat": {
            "missedCallsOpen": int(chat.get("missedCallsOpen") or 0),
            "callbackRequestsOpen": int(chat.get("callbackRequestsOpen") or 0),
            "totalOpen": int(chat.get("totalOpen") or 0),
            "items": list(chat.get("items") or [])[:6],
        },
        "hr": {
            "pendingLeave": int(hr.get("pendingLeave") or 0),
            "expiringDocuments": int(hr.get("expiringDocuments") or 0),
            "inReviewDocuments": int(hr.get("inReviewDocuments") or 0),
            "totalOpen": int(hr.get("totalOpen") or 0),
            "items": list(hr.get("items") or [])[:6],
        },
    }


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

    def _safe(label: str, fn, fallback):
        try:
            return fn()
        except Exception:
            logging.getLogger(__name__).exception("copilot context %s failed for %s", label, company_id)
            return fallback

    return {
        "date": today,
        "workersOnSite": _safe("on_site", lambda: count_on_site(db, company_id, today), 0),
        "onSiteWorkers": _safe("on_site_workers", lambda: list_on_site_workers(db, company_id, today)[:30], []),
        "siteIntelligence": _safe("site_intelligence", lambda: build_site_intelligence(db, company_id), {}),
        "security": _safe("security", lambda: analyze_security(db, company_id, persist=False), {"findings": [], "openAlerts": []}),
        "digitalTwinSummary": _safe(
            "digital_twin",
            lambda: (build_digital_twin(db, company_id) or {}).get("summary"),
            {},
        ),
        "reputationTop5": _safe(
            "reputation",
            lambda: (build_reputation_leaderboard(db, company_id, limit=20) or {}).get("workers", [])[:5],
            [],
        ),
        "activeEmergency": active_emergency,
        "identity": _safe("identity", lambda: build_identity_hub(db, company_id), {}),
        "commandCenter": _safe("command_center", lambda: build_command_center(db, company_id=company_id, role=role), {}),
        "dailyBrief": _daily_brief_for_copilot(db, company_id),
    }


def copilot_query(db, company_id: str, question: str, role: str = "company-admin") -> dict[str, Any]:
    from backend.app.platform.ai.assistant import is_ai_configured, natural_language_query
    from backend.app.platform.ai.context_builder import build_compact_context, infer_context_sources

    ctx = build_compact_context(db, company_id, role)
    if not is_ai_configured():
        return {
            "configured": False,
            "hint": "Set OPENAI_API_KEY to enable natural language answers.",
            "context": ctx,
            "deterministicAnswers": _deterministic_qa(ctx, question),
        }
    result = natural_language_query(company_id, question, ctx)
    sec = ctx.get("security") or {}
    result["contextSummary"] = {
        "workersOnSite": ctx.get("workersOnSite", 0),
        "openSecurityFindings": int(sec.get("openFindings") or 0),
        "operationalIssues": len(ctx.get("operationalIssues") or []),
        "sources": infer_context_sources(ctx),
    }
    return result


def _brief(ctx: dict) -> dict[str, Any]:
    return ctx.get("dailyBrief") or {}


def _deterministic_qa(ctx: dict, question: str) -> dict[str, Any]:
    q = question.lower()
    brief = _brief(ctx)
    att = brief.get("attendance") or {}
    sec_b = brief.get("security") or {}
    chat = brief.get("chat") or {}
    hr = brief.get("hr") or {}

    if "inside" in q or "on site" in q or "vor ort" in q or "anwesend" in q or "موقع" in q or "داخل" in q:
        on_site = att.get("onSite")
        if on_site is None:
            on_site = ctx.get("workersOnSite", 0)
        return {"answer": f"{on_site} workers currently on site.", "source": "live_access_logs"}

    if (
        "fehlt" in q
        or "missing" in q
        or "nicht eingecheckt" in q
        or "absenz" in q
        or ("erwart" in q and ("fehlt" in q or "check" in q))
    ):
        missing_n = int(att.get("missingExpected") or 0)
        names = [
            str(w.get("name") or w.get("workerId") or "").strip()
            for w in (att.get("missingWorkers") or [])[:5]
            if str(w.get("name") or w.get("workerId") or "").strip()
        ]
        name_bit = f" ({', '.join(names)})" if names else ""
        return {
            "answer": (
                f"Erwartet heute: {int(att.get('expectedToday') or 0)}, "
                f"fehlt / kein Check-in: {missing_n}{name_bit}. "
                "Inbox-Filter Anwesenheit · kein Auto-Check-in."
            ),
            "source": "daily_brief.attendance",
        }

    if "late" in q or "spät" in q or "verspät" in q or "متأخر" in q or "außerhalb" in q or "outside" in q:
        late_n = int(att.get("lateToday") or 0)
        outside_n = int(att.get("outsideHoursAttemptsToday") or 0)
        names = [
            str(w.get("name") or w.get("workerId") or "").strip()
            for w in (att.get("lateWorkers") or [])[:5]
            if str(w.get("name") or w.get("workerId") or "").strip()
        ]
        if late_n or outside_n or names:
            name_bit = f" Spät u. a.: {', '.join(names)}." if names else ""
            return {
                "answer": (
                    f"Anwesenheit heute: {late_n} spät, {outside_n} außerhalb Firmenzeiten."
                    f"{name_bit} Firmenzeiten flexibel — Details im Lagebild."
                ),
                "source": "daily_brief.attendance",
            }
        issues = ctx.get("operationalIssues") or ctx.get("siteIntelligence", {}).get("operationalIssues", [])
        return {"answer": issues or "Keine Verspätungen / Außerhalb-Versuche in den heutigen Brief-Daten.", "source": "site_intelligence"}

    if (
        "rückruf" in q
        or "callback" in q
        or "verpasst" in q
        or "missed call" in q
        or "anruf" in q
        or ("chat" in q and ("offen" in q or "call" in q or "anruf" in q))
        or "voice" in q
    ):
        missed = int(chat.get("missedCallsOpen") or 0)
        callbacks = int(chat.get("callbackRequestsOpen") or 0)
        items = chat.get("items") or []
        bits = []
        for it in items[:4]:
            who = str(it.get("workerName") or it.get("workerId") or "").strip()
            kind = "Rückruf" if it.get("kind") == "callback_requested" else "Verpasst"
            if who:
                bits.append(f"{kind}: {who}")
        detail = (" · " + "; ".join(bits)) if bits else ""
        return {
            "answer": (
                f"Chat/Anrufe offen: {int(chat.get('totalOpen') or 0)} "
                f"(verpasst {missed}, Rückruf {callbacks}).{detail} "
                "Kein Auto-Dial — Inbox Chat oder /admin-v2/chat.html."
            ),
            "source": "daily_brief.chat",
        }

    if (
        "urlaub" in q
        or "leave" in q
        or "dokument" in q
        or "document" in q
        or ("hr" in q and ("offen" in q or "pending" in q or "ablauf" in q or "expir" in q))
        or "ablauf" in q
        or "expir" in q
    ):
        leave_n = int(hr.get("pendingLeave") or ctx.get("pendingLeave") or 0)
        docs_n = int(hr.get("expiringDocuments") or 0)
        review_n = int(hr.get("inReviewDocuments") or 0)
        bits = []
        for it in (hr.get("items") or [])[:4]:
            who = str(it.get("workerName") or it.get("workerId") or "").strip()
            if it.get("kind") == "leave":
                bits.append(f"Urlaub: {who or '—'}")
            elif it.get("kind") == "docs_review":
                bits.append(f"Prüfung: {it.get('docTitle') or 'Dokument'}")
            else:
                bits.append(f"Doc: {who or '—'} ({it.get('docType') or 'Dokument'} bis {it.get('expiryDate') or '—'})")
        detail = (" · " + "; ".join(bits)) if bits else ""
        return {
            "answer": (
                f"HR offen: {int(hr.get('totalOpen') or (leave_n + docs_n + review_n))} "
                f"(Urlaub {leave_n}, Docs ablaufend {docs_n}, in Prüfung {review_n}).{detail} "
                "Kein Auto-Approve — Inbox Dokumente oder /admin-v2/docs.html?status=in_review."
            ),
            "source": "daily_brief.hr",
        }

    if (
        "camera" in q
        or "kamera" in q
        or "escalat" in q
        or "wächter" in q
        or "watch" in q
    ):
        cam = sec_b.get("openCameraEscalations")
        if cam is None:
            cam = (ctx.get("commandCenter") or {}).get("openCameraEscalations")
        if cam is None:
            cam = (ctx.get("digitalTwinSummary") or {}).get("openCameraEscalations")
        sec = ctx.get("security") or {}
        n_sec = int(sec.get("openFindings") or len(sec.get("findings") or []) or 0)
        return {
            "answer": (
                f"Camera/security snapshot: open camera escalations≈{cam if cam is not None else 'n/a'}, "
                f"security findings={n_sec}. Assisted police only — no auto-dial. "
                "Open /admin-v2/camera-watch.html for details."
            ),
            "source": "camera_watch",
        }
    if "compliance" in q or "مخاطر" in q or "risk" in q or "security" in q or "sicherheit" in q:
        sec = ctx.get("security", {})
        n = int(sec.get("openFindings") or len(sec.get("findings") or []))
        open_sec = int(sec_b.get("totalOpen") or 0)
        return {
            "answer": (
                f"{n} security findings; brief open security items={open_sec}. "
                "Check Security-Inbox / Kamera-Wächter."
            ),
            "source": "security_engine",
        }
    if "emergency" in q or "notfall" in q or "طوارئ" in q:
        em = ctx.get("activeEmergency") or ctx.get("emergency")
        if isinstance(em, dict) and (em.get("active") or em.get("summary")):
            return {"answer": em.get("summary") or "Active emergency.", "source": "emergency"}
        if em and not isinstance(em, dict):
            return {"answer": str(em), "source": "emergency"}
        return {"answer": "No active emergency.", "source": "emergency"}
    if "lage" in q or "brief" in q or "übersicht" in q or "overview" in q or "zusammenfass" in q:
        on_site = att.get("onSite")
        if on_site is None:
            on_site = ctx.get("workersOnSite", 0)
        sec = ctx.get("security") or {}
        n = int(sec.get("openFindings") or len(sec.get("findings") or []) or 0)
        return {
            "answer": (
                f"Lage heute: {on_site} vor Ort · "
                f"fehlt {int(att.get('missingExpected') or 0)} · spät {int(att.get('lateToday') or 0)} · "
                f"Security offen {int(sec_b.get('totalOpen') or n)} · "
                f"Chat/Anrufe {int(chat.get('totalOpen') or 0)} · "
                f"HR {int(hr.get('totalOpen') or 0)} "
                f"(Urlaub {int(hr.get('pendingLeave') or ctx.get('pendingLeave') or 0)}, "
                f"Docs {int(hr.get('expiringDocuments') or 0)}, "
                f"Prüfung {int(hr.get('inReviewDocuments') or 0)}). "
                "Kein Auto-Dial / kein Auto-Approve. Details: Lagebild / Inbox."
            ),
            "source": "daily_brief",
        }
    return {"answer": None, "source": "needs_llm"}
