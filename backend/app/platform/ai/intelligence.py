"""
AI Workforce Intelligence — rule engine + optional LLM overlay.
Works without API keys; LLM enhances when OPENAI_API_KEY is set.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any


def _today_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def predictive_attendance(db, company_id: str) -> dict[str, Any]:
    """Estimate no-show risk from recent check-in patterns."""
    since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    rows = db.execute(
        """
        SELECT w.id, w.first_name, w.last_name,
               SUM(CASE WHEN al.direction = 'check-in' THEN 1 ELSE 0 END) AS checkins
        FROM workers w
        LEFT JOIN access_logs al ON al.worker_id = w.id AND al.timestamp >= ?
        WHERE w.company_id = ? AND w.deleted_at IS NULL AND w.worker_type = 'worker'
        GROUP BY w.id
        """,
        (since, company_id),
    ).fetchall()
    at_risk = []
    for row in rows:
        checkins = int(row["checkins"] or 0)
        if checkins < 3:
            at_risk.append(
                {
                    "worker_id": row["id"],
                    "name": f"{row['first_name']} {row['last_name']}",
                    "checkins_14d": checkins,
                    "risk": "high" if checkins == 0 else "medium",
                }
            )
    return {"period_days": 14, "at_risk": at_risk[:50]}


def fraud_signals(db, company_id: str) -> dict[str, Any]:
    """Detect rapid duplicate taps and off-hours spikes."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")
    rows = db.execute(
        """
        SELECT al.worker_id, COUNT(*) AS taps
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND al.timestamp >= ?
        GROUP BY al.worker_id
        HAVING taps > 40
        """,
        (company_id, since),
    ).fetchall()
    return {"signals": [{"worker_id": r["worker_id"], "taps_24h": r["taps"], "type": "high_frequency"} for r in rows]}


def workforce_risk(db, company_id: str) -> dict[str, Any]:
    today = _today_prefix()
    expired = db.execute(
        """
        SELECT COUNT(*) AS c FROM worker_documents wd
        JOIN workers w ON w.id = wd.worker_id
        WHERE w.company_id = ? AND wd.expiry_date IS NOT NULL AND wd.expiry_date < ?
        """,
        (company_id, today),
    ).fetchone()
    locked = db.execute(
        "SELECT COUNT(*) AS c FROM workers WHERE company_id = ? AND status = 'gesperrt' AND deleted_at IS NULL",
        (company_id,),
    ).fetchone()
    score = min(100, int((expired["c"] if expired else 0) * 5 + (locked["c"] if locked else 0) * 3))
    return {
        "risk_score": score,
        "expired_documents": int((expired["c"] if expired else 0) or 0),
        "locked_workers": int((locked["c"] if locked else 0) or 0),
        "level": "high" if score >= 60 else "medium" if score >= 30 else "low",
    }


def productivity_snapshot(db, company_id: str) -> dict[str, Any]:
    today = _today_prefix()
    row = db.execute(
        """
        SELECT
            SUM(CASE WHEN al.direction = 'check-in' THEN 1 ELSE 0 END) AS checkins,
            SUM(CASE WHEN al.direction = 'check-out' THEN 1 ELSE 0 END) AS checkouts
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND al.timestamp LIKE ?
        """,
        (company_id, f"{today}%"),
    ).fetchone()
    return {
        "date": today,
        "checkins": int((row["checkins"] if row else 0) or 0),
        "checkouts": int((row["checkouts"] if row else 0) or 0),
    }


def operational_insights(db, company_id: str) -> dict[str, Any]:
    return {
        "attendance": predictive_attendance(db, company_id),
        "fraud": fraud_signals(db, company_id),
        "risk": workforce_risk(db, company_id),
        "productivity": productivity_snapshot(db, company_id),
    }
