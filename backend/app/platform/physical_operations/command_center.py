"""Workforce Command Center — global real-time operations (multi-company for superadmin)."""
from __future__ import annotations

from typing import Any

from ._common import count_on_site, today_prefix


def _count_map(db, sql: str, params: tuple[Any, ...] = ()) -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        for row in db.execute(sql, params).fetchall():
            cid = str(row["company_id"] or "").strip()
            if cid:
                out[cid] = int(row["c"] or 0)
    except Exception:
        pass
    return out


def build_command_center(db, *, company_id: str | None = None, role: str = "company-admin") -> dict[str, Any]:
    today = today_prefix()
    global_scope = role == "superadmin" and not company_id

    if global_scope:
        # Keep global overview light — N+1 on-site/gate scans over 200 firms made Ops hang 10s+.
        companies = db.execute(
            """
            SELECT id, name, status FROM companies
            WHERE (deleted_at IS NULL OR deleted_at = '') AND status != 'deleted'
            ORDER BY name LIMIT 40
            """
        ).fetchall()
    elif company_id:
        companies = db.execute("SELECT id, name, status FROM companies WHERE id = ?", (company_id,)).fetchall()
    else:
        companies = []

    company_ids = [str(dict(raw).get("id") or "").strip() for raw in companies]
    company_ids = [cid for cid in company_ids if cid]

    emg_by = _count_map(
        db,
        """
        SELECT company_id, COUNT(*) AS c FROM emergency_events
        WHERE status = 'active'
        GROUP BY company_id
        """,
    )
    sec_by = _count_map(
        db,
        """
        SELECT company_id, COUNT(*) AS c FROM security_alerts
        WHERE status = 'open'
        GROUP BY company_id
        """,
    )

    company_snapshots = []
    total_on_site = 0
    open_emergencies = 0
    open_security = 0

    if global_scope:
        # Skip expensive per-company presence / gate scans for the all-firms view.
        for raw in companies:
            c = dict(raw)
            cid = str(c.get("id") or "").strip()
            emg = int(emg_by.get(cid, 0))
            sec = int(sec_by.get(cid, 0))
            open_emergencies += emg
            open_security += sec
            company_snapshots.append(
                {
                    "companyId": cid,
                    "name": c.get("name"),
                    "status": c.get("status"),
                    "workersOnSite": 0,
                    "activeGatesToday": 0,
                    "activeEmergencies": emg,
                    "openSecurityAlerts": sec,
                }
            )
        try:
            total_on_site = int(count_on_site_all(db, today) or 0)
        except Exception:
            total_on_site = 0
    else:
        for raw in companies:
            c = dict(raw)
            cid = str(c.get("id") or "").strip()
            on_site = count_on_site(db, cid, today)
            total_on_site += on_site
            emg = int(emg_by.get(cid, 0))
            sec = int(sec_by.get(cid, 0))
            open_emergencies += emg
            open_security += sec
            gates_c = 0
            try:
                gates = db.execute(
                    """
                    SELECT COUNT(DISTINCT TRIM(al.gate)) AS c FROM access_logs al
                    JOIN workers w ON w.id = al.worker_id
                    WHERE w.company_id = ? AND al.timestamp LIKE ?
                    """,
                    (cid, f"{today}%"),
                ).fetchone()
                gates_c = int((gates["c"] if gates else 0) or 0)
            except Exception:
                gates_c = 0
            company_snapshots.append(
                {
                    "companyId": cid,
                    "name": c.get("name"),
                    "status": c.get("status"),
                    "workersOnSite": on_site,
                    "activeGatesToday": gates_c,
                    "activeEmergencies": emg,
                    "openSecurityAlerts": sec,
                }
            )

    recent_events = []
    try:
        from backend.app.platform.events.bus import list_recent_events

        if company_id:
            recent_events = list_recent_events(company_id, limit=30)
        else:
            rows = db.execute(
                """
                SELECT company_id, event_type, payload_json, created_at
                FROM platform_events
                ORDER BY created_at DESC
                LIMIT 30
                """
            ).fetchall()
            recent_events = [dict(r) for r in rows]
    except Exception:
        pass

    alerts = []
    try:
        if company_id:
            rows = db.execute(
                """
                SELECT id, company_id, severity, title, alert_type, created_at
                FROM security_alerts
                WHERE status = 'open' AND company_id = ?
                ORDER BY created_at DESC LIMIT 20
                """,
                (str(company_id).strip(),),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT id, company_id, severity, title, alert_type, created_at
                FROM security_alerts
                WHERE status = 'open'
                ORDER BY created_at DESC LIMIT 20
                """
            ).fetchall()
        alerts = [dict(r) for r in rows]
    except Exception:
        pass

    return {
        "layer": "workforce_command_center",
        "status": "live",
        "date": today,
        "scope": "global" if global_scope else "company",
        "totals": {
            "companies": len(company_snapshots),
            "workersOnSite": total_on_site,
            "activeEmergencies": open_emergencies,
            "openSecurityAlerts": open_security,
        },
        "companies": company_snapshots,
        "recentEvents": recent_events,
        "securityAlerts": alerts,
        "fastGlobal": bool(global_scope),
    }


def count_on_site_all(db, today: str | None = None) -> int:
    """Single aggregate on-site count across all companies (global Ops overview)."""
    from ._common import count_on_site_filtered

    return count_on_site_filtered(db, "", [], today)
