"""
Workforce optimization, scheduling hints, predictive planning (rule-based).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def workforce_optimization(db, company_id: int) -> dict[str, Any]:
    from backend.app.platform.physical_operations._common import count_on_site

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active_workers = db.execute(
        "SELECT COUNT(*) AS c FROM workers WHERE company_id = ? AND deleted_at IS NULL AND status = 'aktiv'",
        (company_id,),
    ).fetchone()
    total = int((active_workers["c"] if active_workers else 0) or 0)
    present = count_on_site(db, str(company_id), today)
    utilization = round(present / max(1, total), 3)
    return {
        "date": today,
        "workersActive": total,
        "workersOnSite": present,
        "utilizationRate": utilization,
        "recommendations": _opt_recommendations(utilization, total, present),
    }


def resource_allocation(db, company_id: int) -> dict[str, Any]:
    rows = db.execute(
        """
        SELECT w.id, w.first_name, w.last_name, COUNT(al.id) AS events
        FROM workers w
        LEFT JOIN access_logs al ON al.worker_id = w.id
            AND al.timestamp >= date('now', '-7 days')
        WHERE w.company_id = ? AND w.deleted_at IS NULL
        GROUP BY w.id
        ORDER BY events ASC
        LIMIT 20
        """,
        (company_id,),
    ).fetchall()
    underused = [dict(r) for r in rows if int(r["events"] or 0) < 3]
    return {"underutilizedWorkers": underused, "suggestedReallocation": len(underused) > 0}


def ai_scheduling_hints(db, company_id: int) -> dict[str, Any]:
    peak = db.execute(
        """
        SELECT substr(al.timestamp, 12, 2) AS hour, COUNT(*) AS c
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND al.timestamp >= date('now', '-14 days')
        GROUP BY hour ORDER BY c DESC LIMIT 1
        """,
        (company_id,),
    ).fetchone()
    return {
        "suggestedShiftStart": f"{(peak['hour'] if peak else '07')}:00",
        "peakHour": peak["hour"] if peak else None,
        "note": "Rule-based hint from access_logs; connect shift_assignments for full scheduling",
    }


def predictive_workforce_plan(db, company_id: int, *, horizon_days: int = 14) -> dict[str, Any]:
    horizon_days = max(1, min(horizon_days, 60))
    since = (datetime.now(timezone.utc) - timedelta(days=horizon_days)).strftime("%Y-%m-%d")
    avg_daily = db.execute(
        """
        SELECT AVG(daily_c) AS avg FROM (
            SELECT substr(al.timestamp, 1, 10) AS d, COUNT(DISTINCT al.worker_id) AS daily_c
            FROM access_logs al
            JOIN workers w ON w.id = al.worker_id
            WHERE w.company_id = ? AND al.timestamp >= ?
            GROUP BY d
        )
        """,
        (company_id, since),
    ).fetchone()
    avg = float((avg_daily["avg"] if avg_daily and avg_daily["avg"] is not None else 0) or 0)
    return {
        "horizonDays": horizon_days,
        "expectedDailyAttendance": round(avg, 1),
        "staffingGapRisk": "high" if avg < 5 else "low",
    }


def _opt_recommendations(utilization: float, total: int, present: int) -> list[str]:
    rec: list[str] = []
    if utilization < 0.4 and total > 10:
        rec.append("Low on-site utilization — review geofence or shift assignments")
    if utilization > 0.95:
        rec.append("Near full attendance — ensure backup gate capacity")
    if not rec:
        rec.append("Workforce levels within expected range")
    return rec
