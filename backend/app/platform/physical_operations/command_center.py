"""Workforce Command Center — global real-time operations (multi-company for superadmin)."""
from __future__ import annotations

from typing import Any

from ._common import count_on_site, today_prefix


def build_command_center(db, *, company_id: int | None = None, role: str = "company-admin") -> dict[str, Any]:
    today = today_prefix()
    if role == "superadmin" and company_id is None:
        companies = db.execute(
            """
            SELECT id, name, status FROM companies
            WHERE (deleted_at IS NULL OR deleted_at = '') AND status != 'deleted'
            ORDER BY name LIMIT 200
            """
        ).fetchall()
    elif company_id:
        companies = db.execute("SELECT id, name, status FROM companies WHERE id = ?", (company_id,)).fetchall()
    else:
        companies = []
    company_snapshots = []
    total_on_site = 0
    open_emergencies = 0
    open_security = 0
    for c in companies:
        cid = int(c["id"])
        on_site = count_on_site(db, cid, today)
        total_on_site += on_site
        emg = 0
        sec = 0
        try:
            emg = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM emergency_events WHERE company_id = ? AND status = 'active'",
                    (cid,),
                ).fetchone()["c"]
                or 0
            )
            sec = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM security_alerts WHERE company_id = ? AND status = 'open'",
                    (cid,),
                ).fetchone()["c"]
                or 0
            )
        except Exception:
            pass
        open_emergencies += emg
        open_security += sec
        gates = db.execute(
            """
            SELECT COUNT(DISTINCT TRIM(al.gate)) AS c FROM access_logs al
            JOIN workers w ON w.id = al.worker_id
            WHERE w.company_id = ? AND al.timestamp LIKE ?
            """,
            (cid, f"{today}%"),
        ).fetchone()
        company_snapshots.append(
            {
                "companyId": cid,
                "name": c["name"],
                "status": c.get("status"),
                "workersOnSite": on_site,
                "activeGatesToday": int((gates["c"] if gates else 0) or 0),
                "activeEmergencies": emg,
                "openSecurityAlerts": sec,
            }
        )
    recent_events = []
    try:
        from backend.app.platform.events.bus import list_recent_events

        if company_id:
            recent_events = list_recent_events(company_id, limit=50)
        else:
            rows = db.execute(
                "SELECT company_id, event_type, payload_json, created_at FROM platform_events ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            recent_events = [dict(r) for r in rows]
    except Exception:
        pass
    alerts = []
    try:
        rows = db.execute(
            """
            SELECT id, company_id, severity, title, alert_type, created_at
            FROM security_alerts WHERE status = 'open'
            ORDER BY created_at DESC LIMIT 30
            """
        ).fetchall()
        if company_id:
            alerts = [dict(r) for r in rows if int(r["company_id"]) == company_id]
        else:
            alerts = [dict(r) for r in rows]
    except Exception:
        pass
    return {
        "layer": "workforce_command_center",
        "status": "live",
        "date": today,
        "scope": "global" if role == "superadmin" and company_id is None else "company",
        "totals": {
            "companies": len(company_snapshots),
            "workersOnSite": total_on_site,
            "activeEmergencies": open_emergencies,
            "openSecurityAlerts": open_security,
        },
        "companies": company_snapshots,
        "recentEvents": recent_events,
        "securityAlerts": alerts,
    }
