"""Daily ops brief: attendance + unified security snapshot for Lagebild."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any


def _today() -> str:
    return date.today().isoformat()


def company_work_window(db, company_id: str) -> dict[str, Any]:
    """Per-company flexible work window (empty = no fixed punctuality hours)."""
    cid = str(company_id or "").strip()
    start = ""
    end = ""
    if cid:
        try:
            row = db.execute(
                "SELECT work_start_time, work_end_time FROM companies WHERE id = ?",
                (cid,),
            ).fetchone()
            if row:
                start = str(row["work_start_time"] or "").strip()[:5]
                end = str(row["work_end_time"] or "").strip()[:5]
        except Exception:
            pass
    if start and len(start) >= 4 and ":" not in start[2:3]:
        start = ""
    if end and len(end) >= 4 and ":" not in end[2:3]:
        end = ""
    return {
        "start": start,
        "end": end,
        "configured": bool(start or end),
        "flexible": not bool(start or end),
        "source": "company" if (start or end) else "unset",
    }


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
    window = company_work_window(db, cid)
    # Soft-fill company window onto expected rows without overwriting Einsatzplan times.
    for w in expected:
        if not w.get("shiftStart") and window.get("start"):
            w["companyStart"] = window["start"]
        if not w.get("shiftEnd") and window.get("end"):
            w["companyEnd"] = window["end"]
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
        "missingWorkers": missing_workers[:40],
        "workWindow": window,
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


def _acked_voice_call_ids(db, company_id: str) -> set[str]:
    """Call IDs already acknowledged in the ops inbox (voice_call_noted)."""
    out: set[str] = set()
    cid = str(company_id or "").strip()
    if not cid:
        return out
    try:
        rows = db.execute(
            """
            SELECT details FROM system_alerts
            WHERE code = 'voice_call_noted'
              AND (details LIKE ? OR details LIKE ?)
            ORDER BY created_at DESC
            LIMIT 300
            """,
            (f'%"{cid}"%', f"%company_id={cid}%"),
        ).fetchall()
        for r in rows:
            raw = r["details"] or ""
            try:
                details = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                details = {}
            if not isinstance(details, dict):
                continue
            detail_cid = str(details.get("companyId") or details.get("company_id") or "").strip()
            if detail_cid and detail_cid != cid:
                continue
            call_id = str(details.get("callId") or details.get("call_id") or "").strip()
            if call_id:
                out.add(call_id)
    except Exception:
        return set()
    return out


def _worker_display_name(db, worker_id: str) -> str:
    wid = str(worker_id or "").strip()
    if not wid:
        return ""
    try:
        row = db.execute(
            """
            SELECT TRIM(COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')) AS worker_name
            FROM workers
            WHERE id = ? AND COALESCE(deleted_at, '') = ''
            """,
            (wid,),
        ).fetchone()
        if not row:
            return wid
        name = str(row["worker_name"] or "").strip()
        return name or wid
    except Exception:
        return wid


def build_chat_brief(db, company_id: str, *, lookback_days: int = 7) -> dict[str, Any]:
    """Open chat/call follow-ups for Lagebild: missed inbound + callback requests."""
    cid = str(company_id or "").strip()
    days = max(1, min(int(lookback_days or 7), 30))
    acked = _acked_voice_call_ids(db, cid) if cid else set()
    missed_items: list[dict[str, Any]] = []
    callback_items: list[dict[str, Any]] = []

    if cid:
        try:
            from backend.app.platform.voice_calls.service import VoiceCallService

            VoiceCallService(db)  # ensure schema
        except Exception:
            pass

        try:
            rows = db.execute(
                """
                SELECT id, worker_id, status, created_at, end_reason, initiated_by
                FROM chat_voice_calls
                WHERE company_id = ?
                  AND COALESCE(initiated_by, 'admin') = 'worker'
                  AND status = 'missed'
                  AND datetime(created_at) >= datetime('now', ?)
                ORDER BY datetime(created_at) DESC
                LIMIT 40
                """,
                (cid, f"-{days} day"),
            ).fetchall()
            for r in rows:
                call_id = str(r["id"] or "").strip()
                if not call_id or call_id in acked:
                    continue
                wid = str(r["worker_id"] or "").strip()
                missed_items.append(
                    {
                        "id": call_id,
                        "kind": "missed_call",
                        "status": "missed",
                        "title": "Verpasster Anruf",
                        "workerId": wid,
                        "workerName": _worker_display_name(db, wid),
                        "createdAt": str(r["created_at"] or ""),
                        "endReason": str(r["end_reason"] or ""),
                        "href": f"/admin-v2/chat.html?company_id={cid}&worker_id={wid}",
                        "source": "chat",
                    }
                )
        except Exception:
            missed_items = []

        try:
            rows = db.execute(
                """
                SELECT id, worker_id, body, created_at
                FROM chat_messages
                WHERE company_id = ?
                  AND body LIKE '%status=callback_requested%'
                  AND datetime(created_at) >= datetime('now', ?)
                ORDER BY datetime(created_at) DESC
                LIMIT 60
                """,
                (cid, f"-{days} day"),
            ).fetchall()
            seen_calls: set[str] = set()
            for r in rows:
                body = str(r["body"] or "")
                call_id = ""
                for part in body.split("|"):
                    if part.startswith("callId="):
                        call_id = part.split("=", 1)[1].strip()
                        break
                if not call_id or call_id in seen_calls or call_id in acked:
                    continue
                seen_calls.add(call_id)
                wid = str(r["worker_id"] or "").strip()
                callback_items.append(
                    {
                        "id": call_id,
                        "kind": "callback_requested",
                        "status": "callback_requested",
                        "title": "Rückruf angefordert",
                        "workerId": wid,
                        "workerName": _worker_display_name(db, wid),
                        "createdAt": str(r["created_at"] or ""),
                        "messageId": str(r["id"] or ""),
                        "href": f"/admin-v2/chat.html?company_id={cid}&worker_id={wid}",
                        "source": "chat",
                    }
                )
        except Exception:
            callback_items = []

    # Prefer callback item when both exist for the same call.
    callback_ids = {str(i.get("id") or "") for i in callback_items}
    missed_items = [i for i in missed_items if str(i.get("id") or "") not in callback_ids]
    items = (callback_items + missed_items)[:16]

    return {
        "missedCallsOpen": len(missed_items),
        "callbackRequestsOpen": len(callback_items),
        "totalOpen": len(items),
        "items": items,
        "lookbackDays": days,
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }


def build_hr_brief(db, company_id: str, *, expiry_days: int = 14) -> dict[str, Any]:
    """Pending leave + expiring worker docs + editor docs in_review for Lagebild."""
    cid = str(company_id or "").strip()
    horizon_days = max(1, min(int(expiry_days or 14), 60))
    leave_items: list[dict[str, Any]] = []
    doc_items: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []

    if cid:
        try:
            rows = db.execute(
                """
                SELECT lr.id, lr.worker_id, lr.type, lr.start_date, lr.end_date,
                       lr.status, lr.created_at,
                       TRIM(COALESCE(w.first_name, '') || ' ' || COALESCE(w.last_name, '')) AS worker_name
                FROM leave_requests lr
                JOIN workers w ON w.id = lr.worker_id
                WHERE (w.company_id = ? OR lr.company_id = ?)
                  AND lr.status IN ('pending', 'ausstehend')
                  AND COALESCE(w.deleted_at, '') = ''
                ORDER BY datetime(lr.created_at) DESC
                LIMIT 30
                """,
                (cid, cid),
            ).fetchall()
            for r in rows:
                lid = str(r["id"] or "").strip()
                wid = str(r["worker_id"] or "").strip()
                name = str(r["worker_name"] or "").strip() or wid
                leave_items.append(
                    {
                        "id": lid,
                        "kind": "leave",
                        "title": "Urlaubsantrag offen",
                        "workerId": wid,
                        "workerName": name,
                        "leaveType": str(r["type"] or ""),
                        "startDate": str(r["start_date"] or "")[:10],
                        "endDate": str(r["end_date"] or "")[:10],
                        "createdAt": str(r["created_at"] or ""),
                        "href": f"/admin-v2/index.html?company_id={cid}&tab=inbox&source=leave",
                        "source": "leave",
                    }
                )
        except Exception:
            leave_items = []

        try:
            from backend.app.platform.physical_operations._common import calendar_day_offset, today_prefix

            horizon = calendar_day_offset(horizon_days)
            today = today_prefix()
            rows = db.execute(
                """
                SELECT wd.id, wd.worker_id, wd.doc_type, wd.expiry_date, wd.created_at,
                       TRIM(COALESCE(w.first_name, '') || ' ' || COALESCE(w.last_name, '')) AS worker_name
                FROM worker_documents wd
                JOIN workers w ON w.id = wd.worker_id
                WHERE w.company_id = ?
                  AND COALESCE(w.deleted_at, '') = ''
                  AND wd.expiry_date IS NOT NULL
                  AND wd.expiry_date <= ?
                  AND wd.expiry_date >= ?
                ORDER BY wd.expiry_date ASC
                LIMIT 40
                """,
                (cid, horizon, today),
            ).fetchall()
            for r in rows:
                did = str(r["id"] or "").strip()
                wid = str(r["worker_id"] or "").strip()
                name = str(r["worker_name"] or "").strip() or wid
                doc_type = str(r["doc_type"] or "Dokument")
                expiry = str(r["expiry_date"] or "")[:10]
                doc_items.append(
                    {
                        "id": did,
                        "kind": "document_expiry",
                        "title": "Dokument läuft ab",
                        "workerId": wid,
                        "workerName": name,
                        "docType": doc_type,
                        "expiryDate": expiry,
                        "createdAt": str(r["created_at"] or ""),
                        "href": f"/admin-v2/docs.html?company_id={cid}",
                        "source": "document",
                    }
                )
        except Exception:
            doc_items = []

        try:
            try:
                from backend.app.domains.docs.repository import EditorDocsRepository

                EditorDocsRepository().ensure_schema(db)
            except Exception:
                pass
            rows = db.execute(
                """
                SELECT id, title, mode, status, updated_at, worker_id, created_at
                FROM editor_documents
                WHERE company_id = ?
                  AND status = 'in_review'
                ORDER BY datetime(COALESCE(updated_at, created_at)) ASC
                LIMIT 40
                """,
                (cid,),
            ).fetchall()
            for r in rows:
                did = str(r["id"] or "").strip()
                if not did:
                    continue
                title = str(r["title"] or "Dokument").strip() or "Dokument"
                review_items.append(
                    {
                        "id": did,
                        "kind": "docs_review",
                        "title": "Dokument zur Prüfung",
                        "docTitle": title,
                        "mode": str(r["mode"] or "general"),
                        "workerId": str(r["worker_id"] or "").strip(),
                        "createdAt": str(r["updated_at"] or r["created_at"] or ""),
                        "href": f"/admin-v2/docs.html?company_id={cid}&id={did}&status=in_review",
                        "source": "document",
                    }
                )
        except Exception:
            review_items = []

    items = (review_items[:8] + leave_items[:6] + doc_items[:6])[:16]
    return {
        "pendingLeave": len(leave_items),
        "expiringDocuments": len(doc_items),
        "inReviewDocuments": len(review_items),
        "expiryDays": horizon_days,
        "totalOpen": len(leave_items) + len(doc_items) + len(review_items),
        "items": items,
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }


def build_daily_ops_brief(db, company_id: str) -> dict[str, Any]:
    attendance = build_attendance_brief(db, company_id)
    security = build_security_brief(db, company_id)
    chat = build_chat_brief(db, company_id)
    hr = build_hr_brief(db, company_id)
    return {
        "ok": True,
        "companyId": str(company_id),
        "attendance": attendance,
        "security": security,
        "chat": chat,
        "hr": hr,
        "autoDial": False,
    }
