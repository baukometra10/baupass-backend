"""Tomorrow workforce forecast — rule-based predictive engine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

_WEEKDAY_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _tomorrow() -> tuple[str, int]:
    t = datetime.now(timezone.utc) + timedelta(days=1)
    return t.strftime("%Y-%m-%d"), t.weekday()


def build_tomorrow_forecast(db, company_id: str) -> dict[str, Any]:
    """Estimate tomorrow on-site headcount and absence drivers."""
    from backend.app.platform.ai.intelligence import predictive_attendance, workforce_risk

    cid = str(company_id or "").strip()
    tomorrow, weekday = _tomorrow()
    drivers: list[dict[str, Any]] = []

    total_active = int(
        db.execute(
            "SELECT COUNT(*) AS c FROM workers WHERE company_id = ? AND deleted_at IS NULL AND worker_type = 'worker'",
            (cid,),
        ).fetchone()["c"]
        or 0
    )

    on_leave: list[dict[str, Any]] = []
    try:
        rows = db.execute(
            """
            SELECT lr.worker_id, lr.type, w.first_name, w.last_name
            FROM leave_requests lr
            JOIN workers w ON w.id = lr.worker_id
            WHERE w.company_id = ?
              AND lr.status = 'genehmigt'
              AND lr.start_date <= ? AND lr.end_date >= ?
            """,
            (cid, tomorrow, tomorrow),
        ).fetchall()
        for r in rows:
            on_leave.append(
                {
                    "workerId": r["worker_id"],
                    "name": f"{r['first_name']} {r['last_name']}".strip(),
                    "type": r["type"],
                }
            )
    except Exception:
        pass
    if on_leave:
        drivers.append({"type": "approved_leave", "count": len(on_leave), "items": on_leave[:8]})

    att = predictive_attendance(db, cid)
    high_risk = [x for x in att.get("at_risk", []) if x.get("risk") == "high"]
    med_risk = [x for x in att.get("at_risk", []) if x.get("risk") == "medium"]
    if high_risk or med_risk:
        drivers.append(
            {
                "type": "attendance_pattern",
                "count": len(high_risk) + len(med_risk),
                "high": len(high_risk),
                "items": (high_risk + med_risk)[:8],
            }
        )

    weekday_factor = 0
    try:
        hist_dates = [
            (datetime.now(timezone.utc) - timedelta(days=7 * i + (datetime.now(timezone.utc).weekday() - weekday) % 7))
            .strftime("%Y-%m-%d")
            for i in range(1, 5)
        ]
        checkins = 0
        for d in hist_dates:
            row = db.execute(
                """
                SELECT COUNT(DISTINCT al.worker_id) AS c
                FROM access_logs al
                JOIN workers w ON w.id = al.worker_id
                WHERE w.company_id = ? AND al.timestamp LIKE ? AND al.direction = 'check-in'
                """,
                (cid, f"{d}%"),
            ).fetchone()
            checkins += int((row["c"] if row else 0) or 0)
        avg_same_weekday = checkins / max(1, len(hist_dates))
        if total_active > 0 and avg_same_weekday < total_active * 0.55:
            weekday_factor = int(total_active * 0.55 - avg_same_weekday)
            drivers.append(
                {
                    "type": "weekday_pattern",
                    "count": weekday_factor,
                    "weekday": _WEEKDAY_DE[weekday],
                    "avgCheckins": round(avg_same_weekday, 1),
                }
            )
    except Exception:
        pass

    risk = workforce_risk(db, cid)
    locked = int(risk.get("locked_workers") or 0)
    if locked:
        drivers.append({"type": "locked_workers", "count": locked})

    expected_absent = len(on_leave) + len(high_risk) + int(len(med_risk) * 0.4) + min(weekday_factor, 5)
    expected_absent = min(total_active, max(0, expected_absent))
    expected_on_site = max(0, total_active - expected_absent)

    recommendations: list[str] = []
    if len(on_leave) >= 3:
        recommendations.append("shift_coverage_review")
    if len(high_risk) >= 2:
        recommendations.append("contact_at_risk_workers")
    if risk.get("level") in ("medium", "high"):
        recommendations.append("renew_expired_documents")
    if expected_absent >= max(3, total_active // 4):
        recommendations.append("notify_foreman")

    summary_de = (
        f"Morgen ({_WEEKDAY_DE[weekday]}, {tomorrow}): ca. {expected_on_site} von {total_active} "
        f"voraussichtlich on-site, {expected_absent} Ausfallrisiko."
    )

    return {
        "date": tomorrow,
        "weekday": weekday,
        "weekdayLabel": _WEEKDAY_DE[weekday],
        "totalActive": total_active,
        "expectedOnSite": expected_on_site,
        "expectedAbsent": expected_absent,
        "confidence": "high" if on_leave else "medium",
        "summary": summary_de,
        "drivers": drivers,
        "recommendations": recommendations,
        "riskLevel": risk.get("level"),
    }
