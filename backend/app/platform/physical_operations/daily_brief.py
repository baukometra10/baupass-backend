"""Daily ops brief: attendance + unified security snapshot for Lagebild."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def _today() -> str:
    return date.today().isoformat()


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

    return {
        "date": today,
        "onSite": on_site,
        "checkInsToday": check_ins,
        "lateToday": len(late_workers),
        "lateWorkers": late_workers[:12],
        "outsideHoursAttemptsToday": outside,
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
