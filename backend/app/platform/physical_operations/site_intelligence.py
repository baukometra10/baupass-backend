"""Smart Site Intelligence — gates, sites, peaks, operational issues."""
from __future__ import annotations

from typing import Any

from ._common import today_prefix


def build_site_intelligence(db, company_id: int) -> dict[str, Any]:
    since_30 = "datetime('now', '-30 day')"
    gate_rows = db.execute(
        f"""
        SELECT COALESCE(NULLIF(TRIM(al.gate), ''), 'Unknown') AS gate,
               COUNT(*) AS total,
               SUM(CASE WHEN al.direction = 'check-in' THEN 1 ELSE 0 END) AS checkins
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND al.timestamp >= {since_30}
        GROUP BY gate ORDER BY total DESC LIMIT 20
        """,
        (company_id,),
    ).fetchall()
    site_rows = db.execute(
        f"""
        SELECT COALESCE(NULLIF(TRIM(w.site), ''), 'Unassigned') AS site,
               COUNT(DISTINCT w.id) AS workers,
               COUNT(al.id) AS access_events
        FROM workers w
        LEFT JOIN access_logs al ON al.worker_id = w.id AND al.timestamp >= {since_30}
        WHERE w.company_id = ? AND w.deleted_at IS NULL
        GROUP BY site ORDER BY access_events ASC
        """,
        (company_id,),
    ).fetchall()
    peak = db.execute(
        f"""
        SELECT substr(al.timestamp, 12, 2) AS hour, COUNT(*) AS c
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND al.direction = 'check-in' AND al.timestamp >= {since_30}
        GROUP BY hour ORDER BY c DESC LIMIT 1
        """,
        (company_id,),
    ).fetchone()
    issues = []
    for s in site_rows:
        events = int(s["access_events"] or 0)
        workers = int(s["workers"] or 0)
        if workers >= 5 and events < workers * 2:
            issues.append(
                {
                    "site": s["site"],
                    "type": "low_activity",
                    "severity": "medium",
                    "message": f"Low access activity vs headcount ({events} events / {workers} workers)",
                }
            )
    if gate_rows:
        top = gate_rows[0]
        if int(top["total"] or 0) > 500:
            issues.append(
                {
                    "gate": top["gate"],
                    "type": "congestion_risk",
                    "severity": "high",
                    "message": f"Gate '{top['gate']}' has {top['total']} events in 30 days",
                }
            )
    return {
        "layer": "smart_site_intelligence",
        "date": today_prefix(),
        "busiestGates": [{"gate": r["gate"], "total": r["total"], "checkins": r["checkins"]} for r in gate_rows[:10]],
        "sitesByProductivity": [
            {"site": r["site"], "workers": r["workers"], "accessEvents": r["access_events"]} for r in site_rows
        ],
        "lowestProductivitySites": [
            {"site": r["site"], "workers": r["workers"], "accessEvents": r["access_events"]}
            for r in site_rows[:5]
        ],
        "peakHour": peak["hour"] if peak else None,
        "peakHourCheckins": int((peak["c"] if peak else 0) or 0),
        "operationalIssues": issues,
    }
