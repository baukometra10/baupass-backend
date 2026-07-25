"""Daily ops brief: attendance + unified security snapshot for Lagebild."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def _today() -> str:
    return date.today().isoformat()


def _checked_in_worker_ids(db, company_id: str, today: str) -> set[str]:
    try:
        rows = db.execute(
            """
            SELECT DISTINCT a.worker_id
            FROM access_logs a
            JOIN workers w ON w.id = a.worker_id
            WHERE w.company_id = ?
              AND COALESCE(w.deleted_at, '') = ''
              AND a.direction = 'check-in'
              AND a.timestamp >= ? AND a.timestamp < date(?, '+1 day')
            """,
            (company_id, today, today),
        ).fetchall()
        return {str(r["worker_id"]) for r in rows if r["worker_id"]}
    except Exception:
        return set()


def _on_leave_ids(db, company_id: str, today: str) -> set[str]:
    try:
        rows = db.execute(
            """
            SELECT lr.worker_id
            FROM leave_requests lr
            JOIN workers w ON w.id = lr.worker_id
            WHERE w.company_id = ?
              AND lr.status = 'genehmigt'
              AND lr.start_date <= ? AND lr.end_date >= ?
            """,
            (company_id, today, today),
        ).fetchall()
        return {str(r["worker_id"]) for r in rows if r["worker_id"]}
    except Exception:
        return set()


def _expected_workers_today(db, company_id: str, today: str) -> list[dict[str, Any]]:
    """Workers expected on site today (deployment plan or Mo–Fr fallback)."""
    cid = str(company_id)
    day = date.fromisoformat(today)
    leave = _on_leave_ids(db, cid, today)
    expected: list[dict[str, Any]] = []

    plan_active = False
    try:
        from backend.app.platform.workforce.attendance_eligibility import (
            company_deployment_plan_active,
            is_real_deployment_location,
        )

        plan_active = bool(company_deployment_plan_active(db, cid, day.year, day.month))
    except Exception:
        plan_active = False
        is_real_deployment_location = None  # type: ignore

    if plan_active:
        try:
            rows = db.execute(
                """
                SELECT d.worker_id, d.location_label, d.shift_start, d.shift_end,
                       TRIM(COALESCE(w.first_name, '') || ' ' || COALESCE(w.last_name, '')) AS worker_name
                FROM worker_deployment_days d
                JOIN workers w ON w.id = d.worker_id
                WHERE d.company_id = ?
                  AND d.work_date = ?
                  AND w.company_id = ?
                  AND COALESCE(w.deleted_at, '') = ''
                  AND COALESCE(w.worker_type, 'worker') = 'worker'
                  AND COALESCE(w.status, 'aktiv') NOT IN ('gesperrt', 'locked', 'inaktiv', 'inactive')
                """,
                (cid, today, cid),
            ).fetchall()
            for r in rows:
                wid = str(r["worker_id"] or "")
                if not wid or wid in leave:
                    continue
                loc = str(r["location_label"] or "")
                if is_real_deployment_location and not is_real_deployment_location(loc):
                    continue
                expected.append(
                    {
                        "workerId": wid,
                        "name": str(r["worker_name"] or "").strip() or wid,
                        "location": loc,
                        "shiftStart": str(r["shift_start"] or "")[:5],
                        "shiftEnd": str(r["shift_end"] or "")[:5],
                        "reason": "scheduled",
                    }
                )
            return expected
        except Exception:
            pass

    # Fallback: active workers on company workdays (Mon–Fri)
    if day.weekday() >= 5:
        return []
    try:
        rows = db.execute(
            """
            SELECT id,
                   TRIM(COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')) AS worker_name
            FROM workers
            WHERE company_id = ?
              AND COALESCE(deleted_at, '') = ''
              AND COALESCE(worker_type, 'worker') = 'worker'
              AND COALESCE(status, 'aktiv') NOT IN ('gesperrt', 'locked', 'inaktiv', 'inactive')
            ORDER BY last_name, first_name
            LIMIT 400
            """,
            (cid,),
        ).fetchall()
        for r in rows:
            wid = str(r["id"] or "")
            if not wid or wid in leave:
                continue
            expected.append(
                {
                    "workerId": wid,
                    "name": str(r["worker_name"] or "").strip() or wid,
                    "location": "",
                    "shiftStart": "",
                    "shiftEnd": "",
                    "reason": "workday",
                }
            )
    except Exception:
        return []
    return expected


def build_attendance_brief(db, company_id: str) -> dict[str, Any]:
    """Who checked in late / on site / check-ins today for one company."""
    cid = str(company_id or "").strip()
    today = _today()
    if not cid:
        return {
            "date": today,
            "onSite": 0,
            "checkInsToday": 0,
            "lateToday": 0,
            "lateWorkers": [],
            "outsideHoursAttemptsToday": 0,
            "expectedToday": 0,
            "missingExpected": 0,
            "missingWorkers": [],
        }

    on_site = 0
    try:
        from backend.app.platform.physical_operations._common import count_on_site

        on_site = int(count_on_site(db, cid, today) or 0)
    except Exception:
        on_site = 0

    check_ins = 0
    try:
        row = db.execute(
            """
            SELECT COUNT(*) AS c
            FROM access_logs a
            JOIN workers w ON w.id = a.worker_id
            WHERE w.company_id = ?
              AND COALESCE(w.deleted_at, '') = ''
              AND a.direction = 'check-in'
              AND a.timestamp >= ? AND a.timestamp < date(?, '+1 day')
            """,
            (cid, today, today),
        ).fetchone()
        check_ins = int((row["c"] if row else 0) or 0)
    except Exception:
        check_ins = 0

    late_workers: list[dict[str, Any]] = []
    try:
        rows = db.execute(
            """
            SELECT a.worker_id, a.timestamp, a.gate,
                   TRIM(COALESCE(w.first_name, '') || ' ' || COALESCE(w.last_name, '')) AS worker_name
            FROM access_logs a
            JOIN workers w ON w.id = a.worker_id
            WHERE w.company_id = ?
              AND COALESCE(w.deleted_at, '') = ''
              AND a.direction = 'check-in'
              AND COALESCE(a.checked_in_late, 0) = 1
              AND a.timestamp >= ? AND a.timestamp < date(?, '+1 day')
            ORDER BY a.timestamp DESC
            LIMIT 25
            """,
            (cid, today, today),
        ).fetchall()
        seen: set[str] = set()
        for r in rows:
            wid = str(r["worker_id"] or "")
            if not wid or wid in seen:
                continue
            seen.add(wid)
            ts = str(r["timestamp"] or "")
            name = str(r["worker_name"] or "").strip() or wid
            late_workers.append(
                {
                    "workerId": wid,
                    "name": name,
                    "at": ts,
                    "time": ts[11:16] if len(ts) >= 16 else "",
                    "gate": str(r["gate"] or "") or "—",
                }
            )
    except Exception:
        late_workers = []

    outside = 0
    try:
        row = db.execute(
            """
            SELECT COUNT(*) AS c FROM system_alerts
            WHERE code = 'outside_hours_checkin_attempt'
              AND resolved_at IS NULL
              AND created_at >= ? AND created_at < date(?, '+1 day')
              AND (
                details LIKE ?
                OR details LIKE ?
                OR details LIKE ?
              )
            """,
            (
                today,
                today,
                f'%"{cid}"%',
                f"%company_id={cid}%",
                f"%companyId={cid}%",
            ),
        ).fetchone()
        outside = int((row["c"] if row else 0) or 0)
    except Exception:
        try:
            row = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM access_logs a
                JOIN workers w ON w.id = a.worker_id
                WHERE w.company_id = ?
                  AND a.direction = 'check-in'
                  AND a.timestamp >= ? AND a.timestamp < date(?, '+1 day')
                  AND (
                    COALESCE(a.note, '') LIKE '%outside%'
                    OR COALESCE(a.note, '') LIKE '%außerhalb%'
                    OR COALESCE(a.gate, '') LIKE '%outside_hours%'
                  )
                """,
                (cid, today, today),
            ).fetchone()
            outside = int((row["c"] if row else 0) or 0)
        except Exception:
            outside = 0

    expected = _expected_workers_today(db, cid, today)
    checked = _checked_in_worker_ids(db, cid, today)
    missing_workers = [w for w in expected if w["workerId"] not in checked]

    return {
        "date": today,
        "onSite": on_site,
        "checkInsToday": check_ins,
        "lateToday": len(late_workers),
        "lateWorkers": late_workers[:12],
        "outsideHoursAttemptsToday": outside,
        "expectedToday": len(expected),
        "missingExpected": len(missing_workers),
        "missingWorkers": missing_workers[:12],
    }


def build_security_brief(db, company_id: str) -> dict[str, Any]:
    """Unified security: camera escalations + AI security open alerts."""
    cid = str(company_id or "").strip()
    open_esc = []
    pending_second = 0
    try:
        from backend.app.platform.physical_operations.camera_escalation import list_escalations

        open_esc = list_escalations(db, cid, limit=20, status="open") or []
        try:
            pending = list_escalations(db, cid, limit=20, status="pending_second_ack") or []
            pending_second = len(pending)
            open_esc = list(open_esc) + list(pending)
        except Exception:
            pass
    except Exception:
        open_esc = []

    security_open = 0
    security_items: list[dict[str, Any]] = []
    try:
        from backend.app.platform.physical_operations.security_engine import analyze_security

        sec = analyze_security(db, cid, persist=False) or {}
        alerts = list(sec.get("openAlerts") or [])
        security_open = len(alerts)
        for a in alerts[:8]:
            security_items.append(
                {
                    "id": a.get("id") or a.get("alert_id"),
                    "title": a.get("title") or a.get("alert_type") or "Security",
                    "severity": a.get("severity") or "high",
                    "source": "security_engine",
                }
            )
    except Exception:
        pass

    cam_items = [
        {
            "id": e.get("id"),
            "title": e.get("cameraName") or e.get("cameraId") or "Kamera",
            "severity": e.get("severity") or "critical",
            "status": e.get("status"),
            "slaLabel": e.get("slaLabel"),
            "source": "camera_watch",
            "href": f"/admin-v2/camera-watch.html?company_id={cid}&escalation={e.get('id')}",
        }
        for e in open_esc[:8]
    ]

    return {
        "openCameraEscalations": len(open_esc),
        "pendingSecondAck": pending_second,
        "openSecurityAlerts": security_open,
        "totalOpen": len(open_esc) + security_open,
        "items": cam_items + security_items,
        "autoDial": False,
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }


def build_daily_ops_brief(db, company_id: str) -> dict[str, Any]:
    attendance = build_attendance_brief(db, company_id)
    security = build_security_brief(db, company_id)
    return {
        "ok": True,
        "companyId": str(company_id),
        "attendance": attendance,
        "security": security,
        "autoDial": False,
    }
