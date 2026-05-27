"""
Behavior pattern analysis from access_logs (rule-based analytics).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def analyze_behavior_patterns(db, company_id: int, *, days: int = 14) -> dict[str, Any]:
    days = max(1, min(days, 90))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    hourly = db.execute(
        """
        SELECT substr(al.timestamp, 12, 2) AS hour, COUNT(*) AS c
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND w.deleted_at IS NULL AND al.timestamp >= ?
        GROUP BY hour
        ORDER BY hour
        """,
        (company_id, since),
    ).fetchall()

    late_checkins = db.execute(
        """
        SELECT COUNT(*) AS c
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND w.deleted_at IS NULL
          AND al.direction = 'check-in' AND al.timestamp >= ?
          AND substr(al.timestamp, 12, 5) > '08:15'
        """,
        (company_id, since),
    ).fetchone()

    weekend = db.execute(
        """
        SELECT COUNT(*) AS c
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND w.deleted_at IS NULL AND al.timestamp >= ?
          AND CAST(strftime('%w', al.timestamp) AS INTEGER) IN (0, 6)
        """,
        (company_id, since),
    ).fetchone()

    peak_hour = None
    peak_count = 0
    for row in hourly:
        c = int(row["c"] if hasattr(row, "__getitem__") else row[1])
        h = row["hour"] if hasattr(row, "__getitem__") else row[0]
        if c > peak_count:
            peak_count = c
            peak_hour = h

    total_checkins = db.execute(
        """
        SELECT COUNT(*) AS c FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND al.direction = 'check-in' AND al.timestamp >= ?
        """,
        (company_id, since),
    ).fetchone()
    total = int((total_checkins["c"] if total_checkins else 0) or 0)
    late = int((late_checkins["c"] if late_checkins else 0) or 0)
    weekend_c = int((weekend["c"] if weekend else 0) or 0)

    risk_score = min(100, int((late / max(1, total)) * 60 + (weekend_c / max(1, total)) * 40))

    return {
        "days": days,
        "since": since,
        "peakHour": peak_hour,
        "peakHourEvents": peak_count,
        "hourlyDistribution": [dict(r) for r in hourly],
        "lateCheckinRate": round(late / max(1, total), 3),
        "weekendActivityRate": round(weekend_c / max(1, total), 3),
        "riskScore": risk_score,
        "insights": _insights(risk_score, peak_hour, late, total),
    }


def _insights(risk: int, peak_hour: str | None, late: int, total: int) -> list[str]:
    out: list[str] = []
    if peak_hour:
        out.append(f"Peak access hour: {peak_hour}:00")
    if total and late / total > 0.15:
        out.append("Elevated late check-in pattern detected")
    if risk >= 70:
        out.append("Review staffing or gate rules for high-risk window")
    if not out:
        out.append("Access patterns within normal range")
    return out
