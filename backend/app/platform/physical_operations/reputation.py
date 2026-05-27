"""Workforce Reputation Score — per-worker commitment, attendance, compliance."""
from __future__ import annotations

import json
from typing import Any

from ._common import now_iso


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 45:
        return "D"
    return "F"


def compute_worker_reputation(db, company_id: int, worker_id: str) -> dict[str, Any]:
    since = "datetime('now', '-30 days')"
    checkins = db.execute(
        f"""
        SELECT COUNT(*) AS c FROM access_logs al
        WHERE al.worker_id = ? AND al.direction = 'check-in' AND al.timestamp >= {since}
        """,
        (worker_id,),
    ).fetchone()
    ci = int((checkins["c"] if checkins else 0) or 0)
    attendance_score = min(40, ci)
    w = db.execute(
        "SELECT status, compliance_signature_data FROM workers WHERE id = ? AND company_id = ?",
        (worker_id, company_id),
    ).fetchone()
    compliance_score = 25
    if w:
        if str(w["status"] or "") == "gesperrt":
            compliance_score = 0
        if not str(w["compliance_signature_data"] or "").strip():
            compliance_score -= 10
    expired = db.execute(
        """
        SELECT COUNT(*) AS c FROM worker_documents wd
        WHERE wd.worker_id = ? AND wd.expiry_date IS NOT NULL AND wd.expiry_date < date('now')
        """,
        (worker_id,),
    ).fetchone()
    if int((expired["c"] if expired else 0) or 0) > 0:
        compliance_score -= 15
    compliance_score = max(0, compliance_score)
    late = db.execute(
        f"""
        SELECT COUNT(*) AS c FROM access_logs al
        WHERE al.worker_id = ? AND al.direction = 'check-in'
          AND CAST(substr(al.timestamp, 12, 2) AS INTEGER) >= 10
          AND al.timestamp >= {since}
        """,
        (worker_id,),
    ).fetchone()
    late_count = int((late["c"] if late else 0) or 0)
    punctuality = max(0, 25 - min(25, late_count * 2))
    fraud_penalty = 0
    taps = db.execute(
        """
        SELECT COUNT(*) AS c FROM access_logs al
        WHERE al.worker_id = ? AND al.timestamp >= datetime('now', '-1 day')
        """,
        (worker_id,),
    ).fetchone()
    if int((taps["c"] if taps else 0) or 0) > 40:
        fraud_penalty = 20
    behavior_score = max(0, 10 - fraud_penalty // 2)
    total = max(0, min(100, attendance_score + compliance_score + punctuality + behavior_score - fraud_penalty))
    breakdown = {
        "attendance": attendance_score,
        "compliance": compliance_score,
        "punctuality": punctuality,
        "behavior": behavior_score,
        "fraudPenalty": fraud_penalty,
        "checkins30d": ci,
        "lateCheckins30d": late_count,
    }
    grade = _grade(total)
    try:
        db.execute(
            """
            INSERT INTO worker_reputation_scores (worker_id, company_id, score, grade, breakdown_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(worker_id, company_id) DO UPDATE SET
                score = excluded.score,
                grade = excluded.grade,
                breakdown_json = excluded.breakdown_json,
                updated_at = excluded.updated_at
            """,
            (worker_id, company_id, total, grade, json.dumps(breakdown), now_iso()),
        )
        db.commit()
    except Exception:
        pass
    return {
        "workerId": worker_id,
        "companyId": company_id,
        "score": total,
        "grade": grade,
        "breakdown": breakdown,
    }


def build_reputation_leaderboard(db, company_id: int, *, limit: int = 100) -> dict[str, Any]:
    workers = db.execute(
        "SELECT id FROM workers WHERE company_id = ? AND deleted_at IS NULL AND worker_type = 'worker' LIMIT ?",
        (company_id, min(limit, 500)),
    ).fetchall()
    scores = [compute_worker_reputation(db, company_id, r["id"]) for r in workers]
    scores.sort(key=lambda x: -x["score"])
    return {
        "layer": "workforce_reputation",
        "companyId": company_id,
        "workers": scores,
        "averageScore": round(sum(s["score"] for s in scores) / max(1, len(scores)), 1),
    }
