"""Email + inbox notifications for camera violations and offline cameras."""
from __future__ import annotations

import html
import json
from typing import Any

from backend.app.platform.notifications.company_mitteilung import _company_admin_recipients


def _notify_admin_inbox(company_id: str, *, title: str, message: str, severity: str) -> None:
    try:
        from backend.app.platform.inbox.events import notify_inbox_changed

        notify_inbox_changed(
            str(company_id),
            source="camera_alert",
            alert_title=title[:120],
            alert_message=message[:240],
            severity=severity,
        )
    except Exception:
        pass


def _send_admin_emails(
    db,
    company_id: str,
    *,
    subject: str,
    text_body: str,
    html_body: str,
    pdf_bytes: bytes | None,
    pdf_filename: str,
) -> int:
    sent = 0
    for recipient in _company_admin_recipients(db, company_id):
        try:
            if pdf_bytes:
                from backend.app.platform.reports.email_delivery import send_pdf_report_email

                ok, _ = send_pdf_report_email(
                    to=recipient,
                    subject=subject,
                    body_text=text_body,
                    pdf_bytes=pdf_bytes,
                    filename=pdf_filename,
                )
            else:
                from backend.app.platform.reports.email_delivery import send_attachments_email

                ok, _ = send_attachments_email(
                    to=recipient,
                    subject=subject,
                    body_text=text_body,
                    attachments=[],
                )
            if ok:
                sent += 1
        except Exception:
            try:
                from backend.server import _send_via_any_api, get_public_base_url

                settings = db.execute(
                    "SELECT smtp_sender_email, smtp_sender_name FROM settings WHERE id = 1"
                ).fetchone()
                sender_email = (settings["smtp_sender_email"] if settings else "") or "noreply@baupass.de"
                sender_name = (settings["smtp_sender_name"] if settings else "") or "BauPass"
                ok, _, _ = _send_via_any_api(
                    subject,
                    sender_email,
                    sender_name,
                    recipient,
                    text_body,
                    html_body,
                )
                if ok:
                    sent += 1
            except Exception:
                pass
    return sent


def notify_camera_violation(
    db,
    *,
    company_id: str,
    event_id: str,
    camera_id: str,
    camera_name: str,
    location: str,
    event_type: str,
    created_at: str,
    analysis: dict[str, Any],
    snapshot_b64: str | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    alerts = list(analysis.get("alerts") or [])
    if not alerts:
        return {"ok": True, "skipped": "no_alerts"}

    company = db.execute("SELECT name FROM companies WHERE id = ?", (str(company_id),)).fetchone()
    company_name = str(company["name"] if company else company_id)
    alert_lines = [str(a.get("message") or a.get("type") or "Alert") for a in alerts]
    summary = alert_lines[0]
    if len(alert_lines) > 1:
        summary = f"{summary} (+{len(alert_lines) - 1} weitere)"

    title = f"Kamera-Alarm: {camera_name or camera_id}"
    message = (
        f"{created_at}: {camera_name or camera_id} ({location or 'Baustelle'}) — "
        f"{event_type}. {summary}"
    )

    try:
        from backend.app.platform.physical_operations.security_engine import _persist_alert

        for alert in alerts:
            _persist_alert(
                db,
                company_id,
                {
                    "alert_type": str(alert.get("type") or "camera_violation"),
                    "severity": alert.get("severity") or "high",
                    "title": str(alert.get("message") or title),
                    "worker_id": worker_id,
                    "details": {
                        "camera_id": camera_id,
                        "event_id": event_id,
                        "event_type": event_type,
                    },
                },
            )
    except Exception:
        pass

    _notify_admin_inbox(str(company_id), title=title, message=message, severity="high")

    pdf_bytes = None
    try:
        from backend.app.platform.reports.camera_pdf import build_camera_incident_pdf

        pdf_bytes = build_camera_incident_pdf(
            company_name=company_name,
            camera_id=camera_id,
            camera_name=camera_name,
            location=location,
            event_type=event_type,
            created_at=created_at,
            alerts=alerts,
            snapshot_b64=snapshot_b64,
            worker_id=worker_id,
        )
    except Exception:
        pdf_bytes = None

    subject = f"BauPass Kamera-Alarm — {camera_name or camera_id}"
    text_body = (
        f"{message}\n\n"
        + "\n".join(f"- {line}" for line in alert_lines)
        + "\n\nBitte Live-Ansicht und Ereignisliste im Control Pass prüfen."
    )
    msg_safe = html.escape(message)
    alerts_html = "".join(f"<li>{html.escape(line)}</li>" for line in alert_lines)
    html_body = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;">
<h2 style="color:#b45309;">{html.escape(title)}</h2>
<p>{msg_safe}</p>
<ul>{alerts_html}</ul>
</body></html>"""

    emails_sent = _send_admin_emails(
        db,
        str(company_id),
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        pdf_bytes=pdf_bytes,
        pdf_filename=f"camera-incident-{event_id}.pdf",
    )

    try:
        from backend.server import log_audit

        log_audit(
            "camera.violation_notified",
            message[:300],
            target_type="camera_event",
            target_id=event_id,
            company_id=company_id,
        )
    except Exception:
        pass

    return {"ok": True, "emailsSent": emails_sent, "eventId": event_id}


def notify_camera_offline(
    db,
    *,
    company_id: str,
    camera_id: str,
    camera_name: str,
    location: str,
    last_seen_at: str | None,
) -> dict[str, Any]:
    company = db.execute("SELECT name FROM companies WHERE id = ?", (str(company_id),)).fetchone()
    company_name = str(company["name"] if company else company_id)
    title = f"Kamera offline: {camera_name or camera_id}"
    message = (
        f"Kamera «{camera_name or camera_id}» ({location or 'Baustelle'}) "
        f"sendet keine Heartbeats mehr. Zuletzt gesehen: {last_seen_at or 'nie'}."
    )

    _notify_admin_inbox(str(company_id), title=title, message=message, severity="warning")

    try:
        from backend.server import create_system_alert

        create_system_alert(
            db,
            code=f"camera_offline_{company_id}_{camera_id}",
            severity="warning",
            message=message[:500],
            details=json.dumps(
                {"companyId": str(company_id), "cameraId": camera_id, "lastSeenAt": last_seen_at},
                ensure_ascii=False,
            ),
            dedup_minutes=60,
        )
    except Exception:
        pass

    pdf_bytes = None
    try:
        from backend.app.platform.reports.camera_pdf import build_camera_digest_pdf

        pdf_bytes = build_camera_digest_pdf(
            company_name=company_name,
            period_label="Offline-Meldung",
            incidents=[],
            offline_cameras=[
                {"id": camera_id, "name": camera_name, "lastSeenAt": last_seen_at},
            ],
        )
    except Exception:
        pdf_bytes = None

    subject = f"BauPass — Kamera offline ({camera_name or camera_id})"
    text_body = message + "\n\nBitte RTSP-Agent / Netzwerk vor Ort prüfen."
    html_body = f"<html><body><p>{html.escape(message)}</p></body></html>"
    emails_sent = _send_admin_emails(
        db,
        str(company_id),
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        pdf_bytes=pdf_bytes,
        pdf_filename=f"camera-offline-{camera_id}.pdf",
    )

    ts = __import__("backend.app.platform.physical_operations._common", fromlist=["now_iso"]).now_iso()
    db.execute(
        """
        UPDATE site_cameras SET offline_alert_sent_at = ?, updated_at = ?
        WHERE company_id = ? AND id = ?
        """,
        (ts, ts, str(company_id), str(camera_id)),
    )
    db.commit()
    return {"ok": True, "emailsSent": emails_sent, "cameraId": camera_id}
