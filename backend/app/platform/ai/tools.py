"""Read-only AI tools — safe live queries against SUPPIX operations data."""
from __future__ import annotations

import json
from typing import Any, Callable

from backend.app.platform.ai.intelligence import (
    fraud_signals,
    operational_insights,
    predictive_attendance,
    workforce_risk,
)
from backend.app.platform.physical_operations._common import list_on_site_workers, today_prefix
from backend.app.platform.physical_operations.security_engine import analyze_security
from backend.app.platform.physical_operations.site_intelligence import build_site_intelligence


def _rows_to_dicts(rows: list) -> list[dict]:
    return [dict(r) for r in rows]


ToolFn = Callable[[Any, str, dict], dict[str, Any]]


def tool_get_on_site_workers(db, company_id: str, _args: dict) -> dict[str, Any]:
    today = today_prefix()
    workers = list_on_site_workers(db, company_id, today)
    return {
        "date": today,
        "count": len(workers),
        "workers": [
            {
                "id": w["id"],
                "name": f"{w.get('first_name', '')} {w.get('last_name', '')}".strip(),
                "site": w.get("site"),
                "gate": w.get("gate"),
                "lastAccess": w.get("last_access"),
                "status": w.get("status"),
            }
            for w in workers[:50]
        ],
    }


def tool_search_workers(db, company_id: str, args: dict) -> dict[str, Any]:
    q = str(args.get("query") or args.get("name") or "").strip()
    if not q:
        return {"error": "query_required", "workers": []}
    like = f"%{q}%"
    rows = db.execute(
        """
        SELECT id, first_name, last_name, site, status, badge_id
        FROM workers
        WHERE company_id = ? AND deleted_at IS NULL
          AND (first_name LIKE ? OR last_name LIKE ? OR badge_id LIKE ? OR id LIKE ?)
        ORDER BY last_name LIMIT 25
        """,
        (company_id, like, like, like, like),
    ).fetchall()
    return {"query": q, "workers": _rows_to_dicts(rows)}


def tool_security_summary(db, company_id: str, _args: dict) -> dict[str, Any]:
    sec = analyze_security(db, company_id, persist=False)
    return {
        "newFindings": sec.get("newFindings", 0),
        "findings": (sec.get("findings") or [])[:20],
        "openAlerts": (sec.get("openAlerts") or [])[:15],
    }


def tool_site_intelligence(db, company_id: str, _args: dict) -> dict[str, Any]:
    data = build_site_intelligence(db, company_id)
    return {
        "operationalIssues": data.get("operationalIssues", [])[:15],
        "busiestGates": data.get("busiestGates", [])[:10],
        "peakHour": data.get("peakHour"),
        "sitesByProductivity": data.get("sitesByProductivity", [])[:10],
    }


def tool_attendance_risk(db, company_id: str, _args: dict) -> dict[str, Any]:
    return predictive_attendance(db, company_id)


def tool_workforce_risk(db, company_id: str, _args: dict) -> dict[str, Any]:
    return workforce_risk(db, company_id)


def tool_fraud_signals(db, company_id: str, _args: dict) -> dict[str, Any]:
    return fraud_signals(db, company_id)


def tool_expired_documents(db, company_id: str, args: dict) -> dict[str, Any]:
    limit = min(50, max(1, int(args.get("limit") or 30)))
    today = today_prefix()
    rows = db.execute(
        """
        SELECT w.id AS worker_id, w.first_name, w.last_name, wd.doc_type, wd.expiry_date
        FROM worker_documents wd
        JOIN workers w ON w.id = wd.worker_id
        WHERE w.company_id = ? AND w.deleted_at IS NULL
          AND wd.expiry_date IS NOT NULL AND wd.expiry_date < ?
        ORDER BY wd.expiry_date ASC LIMIT ?
        """,
        (company_id, today, limit),
    ).fetchall()
    return {"expired": _rows_to_dicts(rows), "count": len(rows)}


def tool_access_timeline_today(db, company_id: str, args: dict) -> dict[str, Any]:
    limit = min(100, max(5, int(args.get("limit") or 40)))
    today = today_prefix()
    rows = db.execute(
        """
        SELECT al.timestamp, al.direction, al.gate, w.id AS worker_id,
               w.first_name, w.last_name
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND al.timestamp LIKE ?
        ORDER BY al.timestamp DESC LIMIT ?
        """,
        (company_id, f"{today}%", limit),
    ).fetchall()
    return {"date": today, "events": _rows_to_dicts(rows)}


def tool_operational_insights(db, company_id: str, _args: dict) -> dict[str, Any]:
    return operational_insights(db, company_id)


def tool_tomorrow_forecast(db, company_id: str, _args: dict) -> dict[str, Any]:
    from backend.app.platform.predictions.engine import build_tomorrow_forecast

    return build_tomorrow_forecast(db, company_id)


def tool_repeated_late_workers(db, company_id: str, args: dict) -> dict[str, Any]:
    from backend.app.platform.workforce.late_streak import list_repeated_late_workers

    min_streak = max(2, min(14, int(args.get("min_streak") or args.get("minStreak") or 3)))
    limit = max(1, min(50, int(args.get("limit") or 10)))
    workers = list_repeated_late_workers(db, company_id, min_streak=min_streak, limit=limit)
    return {"minStreak": min_streak, "count": len(workers), "workers": workers}


def tool_outside_hours_attempts(db, company_id: str, args: dict) -> dict[str, Any]:
    hours = max(1, min(168, int(args.get("hours") or 24)))
    limit = max(1, min(80, int(args.get("limit") or 40)))
    items: list[dict[str, Any]] = []
    try:
        rows = db.execute(
            """
            SELECT id, code, severity, message, details, created_at
            FROM system_alerts
            WHERE code = 'outside_hours_checkin_attempt'
              AND resolved_at IS NULL
            ORDER BY created_at DESC
            LIMIT 120
            """
        ).fetchall()
        for row in rows:
            details = {}
            try:
                details = json.loads(row["details"] or "{}")
            except Exception:
                details = {}
            if str(details.get("companyId") or "") != str(company_id):
                continue
            items.append(
                {
                    "id": row["id"],
                    "title": row["code"],
                    "body": (row["message"] or "")[:240],
                    "severity": row["severity"],
                    "createdAt": row["created_at"],
                    "workerId": details.get("workerId"),
                    "channel": details.get("channel"),
                    "gate": details.get("gate"),
                }
            )
            if len(items) >= limit:
                break
    except Exception:
        items = []
    return {"hours": hours, "count": len(items), "attempts": items}


def tool_presence_summary(db, company_id: str, _args: dict) -> dict[str, Any]:
    today = today_prefix()
    on_site = list_on_site_workers(db, company_id, today)
    open_sessions = []
    try:
        rows = db.execute(
            """
            SELECT worker_id, open_direction, last_checkin_at, last_checkout_at, updated_at
            FROM worker_presence_state
            WHERE company_id = ? AND open_direction = 'check-in'
            ORDER BY last_checkin_at DESC
            LIMIT 100
            """,
            (company_id,),
        ).fetchall()
        open_sessions = _rows_to_dicts(rows)
    except Exception:
        open_sessions = []
    by_site: dict[str, int] = {}
    for w in on_site:
        site = str(w.get("site") or "—")
        by_site[site] = by_site.get(site, 0) + 1
    return {
        "date": today,
        "onSiteCount": len(on_site),
        "openPresenceCount": len(open_sessions),
        "bySite": [{"site": k, "count": v} for k, v in sorted(by_site.items(), key=lambda x: -x[1])],
        "openSessions": open_sessions[:40],
    }


def tool_browse_inbox(db, company_id: str, args: dict) -> dict[str, Any]:
    from backend.app.platform.inbox.service import build_operations_inbox

    limit = max(5, min(80, int(args.get("limit") or 40)))
    source = str(args.get("source") or "").strip() or None
    inbox = build_operations_inbox(
        db,
        company_id,
        limit=limit,
        source_filter=source,
    )
    items = inbox.get("items") if isinstance(inbox, dict) else []
    if not isinstance(items, list):
        items = []
    return {
        "count": len(items),
        "source": source,
        "items": items[:limit],
        "summary": (inbox.get("summary") if isinstance(inbox, dict) else None),
    }


def tool_worker_profile(db, company_id: str, args: dict) -> dict[str, Any]:
    wid = str(args.get("worker_id") or "").strip()
    if not wid:
        return {"error": "worker_id_required"}
    w = db.execute(
        """
        SELECT id, first_name, last_name, site, status, badge_id, worker_type, valid_until
        FROM workers WHERE id = ? AND company_id = ? AND deleted_at IS NULL
        """,
        (wid, company_id),
    ).fetchone()
    if not w:
        return {"error": "worker_not_found"}
    docs = db.execute(
        "SELECT doc_type, expiry_date FROM worker_documents WHERE worker_id = ? ORDER BY expiry_date",
        (wid,),
    ).fetchall()
    recent = db.execute(
        """
        SELECT direction, gate, timestamp FROM access_logs
        WHERE worker_id = ? ORDER BY timestamp DESC LIMIT 15
        """,
        (wid,),
    ).fetchall()
    return {
        "worker": dict(w),
        "documents": _rows_to_dicts(docs),
        "recentAccess": _rows_to_dicts(recent),
    }


TOOL_HANDLERS: dict[str, ToolFn] = {
    "get_on_site_workers": tool_get_on_site_workers,
    "search_workers": tool_search_workers,
    "get_security_summary": tool_security_summary,
    "get_site_intelligence": tool_site_intelligence,
    "get_attendance_risk": tool_attendance_risk,
    "get_workforce_risk": tool_workforce_risk,
    "get_fraud_signals": tool_fraud_signals,
    "get_expired_documents": tool_expired_documents,
    "get_access_timeline_today": tool_access_timeline_today,
    "get_operational_insights": tool_operational_insights,
    "get_worker_profile": tool_worker_profile,
    "get_tomorrow_forecast": tool_tomorrow_forecast,
    "get_repeated_late_workers": tool_repeated_late_workers,
    "get_outside_hours_attempts": tool_outside_hours_attempts,
    "get_presence_summary": tool_presence_summary,
    "browse_inbox": tool_browse_inbox,
}


OPENAI_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_on_site_workers",
            "description": "List workers currently checked in on site today.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_workers",
            "description": "Search workers by name, badge id, or worker id.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Name or badge fragment"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_worker_profile",
            "description": "Full profile for one worker: status, documents, recent access.",
            "parameters": {
                "type": "object",
                "properties": {"worker_id": {"type": "string"}},
                "required": ["worker_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_security_summary",
            "description": "Security findings and open alerts for the company.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_site_intelligence",
            "description": "Gate traffic, site productivity issues, peak hours.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_attendance_risk",
            "description": "Workers at risk of no-show based on 14-day check-in patterns.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_workforce_risk",
            "description": "Compliance risk score: expired docs, locked workers.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fraud_signals",
            "description": "Suspicious high-frequency access taps in last 24h.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_expired_documents",
            "description": "Worker documents past expiry date.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_access_timeline_today",
            "description": "Recent check-in/check-out events today.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_operational_insights",
            "description": "Combined attendance, fraud, risk, productivity snapshot.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tomorrow_forecast",
            "description": "Tomorrow staffing/absence forecast and risk drivers.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_repeated_late_workers",
            "description": "Workers with consecutive late check-in streaks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_streak": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_outside_hours_attempts",
            "description": "Recent outside-working-hours check-in attempts (employer alerts).",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_presence_summary",
            "description": "Who is currently on site / has an open check-in session.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse_inbox",
            "description": "Browse open operations inbox items (alerts, leave, forecasts).",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
    },
]


def run_tool(db, company_id: str, name: str, arguments: dict | str | None) -> dict[str, Any]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return {"error": "unknown_tool", "tool": name}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            arguments = {}
    args = arguments if isinstance(arguments, dict) else {}
    try:
        return handler(db, company_id, args)
    except Exception as exc:
        return {"error": "tool_failed", "tool": name, "message": str(exc)[:300]}
