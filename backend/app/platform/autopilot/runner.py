"""Scheduled autopilot — ack stale alerts, doc pushes, security scan, default reports."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .settings import get_settings
from .seed_rules import ensure_company_automation_rules


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _recent_autopilot_audit(db, company_id: str, event_type: str, target_id: str, hours: int = 168) -> bool:
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = db.execute(
            """
            SELECT id FROM audit_logs
            WHERE company_id = ? AND event_type = ? AND target_id = ?
              AND created_at >= ?
            LIMIT 1
            """,
            (str(company_id), event_type, target_id, since),
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _log_autopilot(db, company_id: str, event_type: str, target_id: str, message: str) -> None:
    try:
        from backend.server import log_audit

        log_audit(
            event_type,
            message,
            company_id=str(company_id),
            target_type="autopilot",
            target_id=target_id,
        )
    except Exception:
        db.execute(
            """
            INSERT INTO audit_logs (id, event_type, actor_user_id, actor_role, company_id, target_type, target_id, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"aud-{uuid.uuid4().hex[:8]}",
                event_type,
                "autopilot",
                "system",
                str(company_id),
                "autopilot",
                target_id,
                message[:500],
                _now_iso(),
            ),
        )
        db.commit()


def _auto_ack_info_alerts(db, company_id: str, after_hours: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, after_hours))).strftime("%Y-%m-%dT%H:%M:%SZ")
    cid = str(company_id)
    try:
        rows = db.execute(
            """
            SELECT id, details FROM system_alerts
            WHERE resolved_at IS NULL
              AND LOWER(COALESCE(severity, '')) = 'info'
              AND created_at < ?
            ORDER BY created_at ASC
            LIMIT 200
            """,
            (cutoff,),
        ).fetchall()
    except Exception:
        return 0
    n = 0
    for r in rows:
        details = str(r["details"] or "")
        if cid not in details and f'"companyId": "{cid}"' not in details and f'"company_id": "{cid}"' not in details:
            if details.strip():
                continue
        db.execute(
            "UPDATE system_alerts SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
            (_now_iso(), r["id"]),
        )
        n += 1
    if n:
        db.commit()
    return n


def _auto_notify_document_expiry(db, company_id: str, horizon_days: int) -> int:
    from backend.app.platform.ai.actions import execute_action
    from backend.app.platform.physical_operations._common import calendar_day_offset, today_prefix

    today_s = today_prefix()
    horizon = calendar_day_offset(max(1, horizon_days))
    try:
        rows = db.execute(
            """
            SELECT wd.id, wd.worker_id, wd.doc_type, wd.expiry_date,
                   w.first_name, w.last_name
            FROM worker_documents wd
            JOIN workers w ON w.id = wd.worker_id
            WHERE w.company_id = ?
              AND wd.expiry_date IS NOT NULL
              AND wd.expiry_date <= ?
              AND wd.expiry_date >= ?
              AND COALESCE(w.status, '') NOT IN ('gesperrt', 'inactive', 'deleted')
            ORDER BY wd.expiry_date ASC
            LIMIT 80
            """,
            (str(company_id), horizon, today_s),
        ).fetchall()
    except Exception:
        return 0

    sent = 0
    for r in rows:
        doc_id = str(r["id"])
        dedup_key = f"doc-{doc_id}"
        if _recent_autopilot_audit(db, company_id, "autopilot.doc_notify", dedup_key, hours=168):
            continue
        name = f"{r['first_name']} {r['last_name']}".strip()
        body = f"{r['doc_type']} läuft ab am {r['expiry_date']}"
        res = execute_action(
            db,
            company_id=str(company_id),
            user_id="autopilot",
            action="notify_worker",
            params={
                "worker_id": r["worker_id"],
                "title": "Dokument läuft ab",
                "body": body,
                "tag": "document-expiry-autopilot",
            },
        )
        if res.get("ok") or int(res.get("pushSent") or 0) > 0:
            sent += 1
            _log_autopilot(
                db,
                company_id,
                "autopilot.doc_notify",
                dedup_key,
                f"Push Dokumentablauf {name} {r['doc_type']}",
            )
    if sent:
        try:
            from backend.app.platform.inbox.events import notify_inbox_changed

            notify_inbox_changed(str(company_id), source="document_expiry")
        except Exception:
            pass
    return sent


def _auto_security_scan(db, company_id: str) -> bool:
    day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _recent_autopilot_audit(db, company_id, "autopilot.security_scan", day_key, hours=20):
        return False
    try:
        from backend.app.platform.physical_operations.security_engine import analyze_security

        report = analyze_security(db, str(company_id), persist=True)
        _log_autopilot(
            db,
            company_id,
            "autopilot.security_scan",
            day_key,
            f"Security-Scan Autopilot: newFindings={report.get('newFindings', 0)}",
        )
        try:
            from backend.app.platform.events.bus import publish_event

            publish_event(
                "autopilot.daily",
                str(company_id),
                {"source": "autopilot", "security": report},
            )
        except Exception:
            pass
        return True
    except Exception:
        return False


def _ensure_scheduled_report_job(db, company_id: str, local_hour: int, timezone: str) -> bool:
    try:
        row = db.execute(
            "SELECT id FROM scheduled_report_jobs WHERE company_id = ? AND enabled = 1 LIMIT 1",
            (str(company_id),),
        ).fetchone()
        if row:
            return False
        admins = db.execute(
            """
            SELECT email FROM users
            WHERE company_id = ? AND role = 'company-admin' AND COALESCE(email, '') != ''
            LIMIT 3
            """,
            (str(company_id),),
        ).fetchall()
        emails = [str(r["email"]).strip() for r in admins if r and str(r["email"]).strip()]
        if not emails:
            return False
        job_id = f"srj-{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        db.execute(
            """
            INSERT INTO scheduled_report_jobs
                (id, company_id, report_type, recipients_json, local_hour, timezone, enabled, attach_datev, last_sent_day, created_at, updated_at)
            VALUES (?, ?, 'daily_ops', ?, ?, ?, 1, 0, NULL, ?, ?)
            """,
            (
                job_id,
                str(company_id),
                json.dumps(emails),
                int(local_hour),
                str(timezone or "Europe/Berlin"),
                now,
                now,
            ),
        )
        db.commit()
        _log_autopilot(
            db,
            company_id,
            "autopilot.scheduled_report_created",
            job_id,
            f"Automatischer Tages-PDF-Job für {', '.join(emails)}",
        )
        return True
    except Exception:
        return False


def run_company_autopilot(db, company_id: str) -> dict[str, Any]:
    settings = get_settings(db, company_id)
    summary: dict[str, Any] = {"companyId": str(company_id), "ok": True}

    if settings.get("autoSeedAutomationRules", True):
        summary["rulesSeeded"] = ensure_company_automation_rules(db, company_id)

    if settings.get("autoAckInfoAlerts", True):
        summary["infoAlertsAcked"] = _auto_ack_info_alerts(
            db, company_id, int(settings.get("autoAckInfoAlertsAfterHours") or 48)
        )

    if settings.get("autoNotifyDocExpiry", True):
        summary["docExpiryPushes"] = _auto_notify_document_expiry(
            db, company_id, int(settings.get("autoNotifyDocExpiryDays") or 14)
        )

    if settings.get("autoDailySecurityScan", True):
        summary["securityScan"] = _auto_security_scan(db, company_id)

    if settings.get("autoEnsureScheduledReport", True):
        summary["scheduledReportCreated"] = _ensure_scheduled_report_job(
            db,
            company_id,
            int(settings.get("scheduledReportLocalHour") or 8),
            str(settings.get("scheduledReportTimezone") or "Europe/Berlin"),
        )

    if settings.get("autoInboxBulkDocPush", True):
        summary["inboxDocPushes"] = _auto_inbox_document_pushes(db, company_id)

    if settings.get("autoInboxAckLowSecurity", False):
        summary["lowSecurityResolved"] = _auto_resolve_low_security(db, company_id)

    if settings.get("autoPrepareNextMonthDeployment", True) and not settings.get("autoSendDeploymentPlans", False):
        summary["nextMonthPrepared"] = _maybe_prepare_next_month_deployment(db, company_id)

    return summary


def _run_survey_invites(db) -> dict[str, Any]:
    try:
        from backend.app.domains.admin.survey_dispatch import run_survey_invite_cycle

        return run_survey_invite_cycle(db)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _maybe_prepare_next_month_deployment(db, company_id: str) -> dict | None:
    """From day 20: draft next month from weekday pattern — never auto-send."""
    from datetime import datetime, timezone

    day = datetime.now(timezone.utc).day
    if day < 20:
        return {"skipped": True, "reason": "before_day_20"}
    try:
        from .settings import get_settings

        if get_settings(db, company_id).get("autoSendDeploymentPlans", False):
            return {"skipped": True, "reason": "auto_send_disabled_by_policy"}
    except Exception:
        pass
    try:
        from backend.app.platform.workforce.deployment_month import get_month_batch, prepare_next_month_draft

        ref = datetime.now(timezone.utc).date()
        ty = ref.year + (1 if ref.month == 12 else 0)
        tm = 1 if ref.month == 12 else ref.month + 1
        batch = get_month_batch(db, company_id, ty, tm)
        if batch.get("exists") and int(
            db.execute(
                """
                SELECT COUNT(*) AS c FROM worker_deployment_days
                WHERE company_id = ? AND work_date LIKE ?
                """,
                (str(company_id), f"{ty:04d}-{tm:02d}-%"),
            ).fetchone()["c"]
            or 0
        ) > 5:
            return {"skipped": True, "reason": "next_month_already_has_data"}
        return prepare_next_month_draft(db, company_id, reference=ref)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _auto_inbox_document_pushes(db, company_id: str) -> int:
    from backend.app.platform.inbox.bulk import run_bulk_inbox_action
    from backend.app.platform.inbox.service import build_operations_inbox

    dash = build_operations_inbox(db, str(company_id), role="company-admin", limit=120)
    doc_items = [it for it in (dash.get("items") or []) if str(it.get("id", "")).startswith("doc:")]
    if not doc_items:
        return 0
    res = run_bulk_inbox_action(
        db,
        company_id=str(company_id),
        user_id="autopilot",
        action="push_document_reminders",
        item_ids=[it["id"] for it in doc_items[:25]],
    )
    return int(res.get("pushSent") or 0)


def _auto_resolve_low_security(db, company_id: str) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        rows = db.execute(
            """
            SELECT id FROM security_alerts
            WHERE company_id = ? AND status = 'open'
              AND LOWER(COALESCE(severity, '')) = 'low'
              AND created_at < ?
            LIMIT 50
            """,
            (str(company_id), cutoff),
        ).fetchall()
    except Exception:
        return 0
    n = 0
    for r in rows:
        db.execute(
            "UPDATE security_alerts SET status = 'resolved', resolved_at = ? WHERE id = ?",
            (_now_iso(), r["id"]),
        )
        n += 1
    if n:
        db.commit()
    return n


def run_autopilot_cycle(db) -> dict[str, Any]:
    """Run autopilot for all active companies."""
    try:
        db.execute("SELECT 1 FROM company_autopilot_settings LIMIT 1")
    except Exception:
        return {"ok": True, "skipped": True, "reason": "no_autopilot_table"}

    try:
        companies = db.execute(
            """
            SELECT id FROM companies
            WHERE COALESCE(status, 'active') NOT IN ('deleted', 'inactive', 'archived')
            ORDER BY id
            """
        ).fetchall()
    except Exception:
        companies = db.execute("SELECT id FROM companies ORDER BY id").fetchall()

    results: list[dict] = []
    totals = {
        "infoAlertsAcked": 0,
        "docExpiryPushes": 0,
        "securityScans": 0,
        "rulesSeeded": 0,
        "scheduledReportsCreated": 0,
        "surveyInvitesSent": 0,
    }
    for row in companies:
        cid = str(row["id"])
        try:
            s = run_company_autopilot(db, cid)
            results.append(s)
            totals["infoAlertsAcked"] += int(s.get("infoAlertsAcked") or 0)
            totals["docExpiryPushes"] += int(s.get("docExpiryPushes") or 0)
            if s.get("securityScan"):
                totals["securityScans"] += 1
            totals["rulesSeeded"] += int(s.get("rulesSeeded") or 0)
            if s.get("scheduledReportCreated"):
                totals["scheduledReportsCreated"] += 1
        except Exception as exc:
            results.append({"companyId": cid, "ok": False, "error": str(exc)[:200]})

    survey_result = _run_survey_invites(db)
    totals["surveyInvitesSent"] = int(survey_result.get("sent") or 0)
    results.append({"surveyInvites": survey_result})

    return {
        "ok": True,
        "companies": len(results),
        "totals": totals,
        "sample": results[:5],
    }
