"""AI Security Engine — suspicious access, fraud, card abuse, anomalies."""
from __future__ import annotations

import json
import uuid
from typing import Any

from backend.app.platform.ai.intelligence import fraud_signals

from ._common import now_iso


def _persist_alert(db, company_id: int, alert: dict) -> str:
    aid = f"sec-{uuid.uuid4().hex[:12]}"
    try:
        db.execute(
            """
            INSERT INTO security_alerts
                (id, company_id, worker_id, alert_type, severity, title, details_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                aid,
                company_id,
                alert.get("worker_id"),
                alert["alert_type"],
                alert.get("severity", "medium"),
                alert["title"],
                json.dumps(alert.get("details") or {}),
                now_iso(),
            ),
        )
        db.commit()
    except Exception:
        pass
    return aid


def analyze_security(db, company_id: int, *, persist: bool = True) -> dict[str, Any]:
    cid = str(company_id)
    findings: list[dict] = []
    fraud = fraud_signals(db, cid)
    for sig in fraud.get("signals", []):
        findings.append(
            {
                "alert_type": "high_frequency_taps",
                "severity": "high",
                "title": "Possible attendance manipulation",
                "worker_id": sig.get("worker_id"),
                "details": sig,
            }
        )
    off_hours = db.execute(
        """
        SELECT al.worker_id, COUNT(*) AS c
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ?
          AND (CAST(substr(al.timestamp, 12, 2) AS INTEGER) < 5
               OR CAST(substr(al.timestamp, 12, 2) AS INTEGER) >= 22)
          AND al.timestamp >= datetime('now', '-7 days')
        GROUP BY al.worker_id
        HAVING c >= 3
        """,
        (company_id,),
    ).fetchall()
    for r in off_hours:
        findings.append(
            {
                "alert_type": "off_hours_access",
                "severity": "medium",
                "title": "Off-hours site access pattern",
                "worker_id": r["worker_id"],
                "details": {"events": r["c"]},
            }
        )
    gate_hop = db.execute(
        """
        SELECT al.worker_id, COUNT(DISTINCT TRIM(al.gate)) AS gates, COUNT(*) AS taps
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND al.timestamp >= datetime('now', '-2 hours')
        GROUP BY al.worker_id
        HAVING gates >= 3 AND taps >= 6
        """,
        (company_id,),
    ).fetchall()
    for r in gate_hop:
        findings.append(
            {
                "alert_type": "abnormal_movement",
                "severity": "high",
                "title": "Rapid multi-gate movement (possible tailgating)",
                "worker_id": r["worker_id"],
                "details": {"gates": r["gates"], "taps": r["taps"]},
            }
        )
    dup_cards = db.execute(
        """
        SELECT w.badge_id, COUNT(DISTINCT w.id) AS workers
        FROM workers w
        WHERE w.company_id = ? AND w.deleted_at IS NULL
          AND TRIM(COALESCE(w.badge_id, '')) != ''
        GROUP BY w.badge_id
        HAVING workers > 1
        """,
        (company_id,),
    ).fetchall()
    for r in dup_cards:
        findings.append(
            {
                "alert_type": "shared_badge_risk",
                "severity": "critical",
                "title": "Duplicate badge ID across workers",
                "worker_id": None,
                "details": {"badge_id": r["badge_id"], "worker_count": r["workers"]},
            }
        )
    alert_ids = []
    if persist:
        for f in findings:
            alert_ids.append(_persist_alert(db, company_id, f))
    open_rows = []
    try:
        open_rows = db.execute(
            """
            SELECT id, alert_type, severity, title, worker_id, status, created_at
            FROM security_alerts
            WHERE company_id = ? AND status = 'open'
            ORDER BY created_at DESC LIMIT 100
            """,
            (company_id,),
        ).fetchall()
    except Exception:
        pass
    return {
        "layer": "ai_security_engine",
        "status": "active",
        "newFindings": len(findings),
        "findings": findings,
        "openAlerts": [dict(r) for r in open_rows],
        "alertIds": alert_ids,
        "capabilities": [
            "suspicious_entry",
            "abnormal_movement",
            "attendance_fraud",
            "shared_badge_detection",
            "off_hours_access",
        ],
    }
