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
                from backend.app.core.platform_env import default_noreply_email
                from backend.server import _send_via_any_api, get_public_base_url

                settings = db.execute(
                    "SELECT smtp_sender_email, smtp_sender_name FROM settings WHERE id = 1"
                ).fetchone()
                sender_email = (settings["smtp_sender_email"] if settings else "") or default_noreply_email()
                sender_name = (settings["smtp_sender_name"] if settings else "") or "WorkPass"
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


def _notify_sms_push(
    db,
    company_id: str,
    *,
    title: str,
    message: str,
    escalation_id: str | None,
    event_id: str = "",
    send_sms_flag: bool = True,
    send_push_flag: bool = True,
) -> dict:
    result = {"sms": False, "push": False}
    if send_sms_flag:
        try:
            from backend.app.platform.security.contracts_lock import company_owner_phone
            from backend.app.platform.notifications.sms import send_sms, sms_configured

            phone = company_owner_phone(db, company_id)
            if phone and sms_configured():
                ok, _ = send_sms(to=phone, body=f"{title}\n{message}"[:300])
                result["sms"] = bool(ok)
        except Exception:
            pass
    if send_push_flag:
        try:
            from backend.app.platform.push.admin_delivery import deliver_admin_push

            esc = escalation_id or event_id or "cam"
            # Deep-link always includes company_id; escalation id when available
            deep = f"/admin-v2/camera-watch.html?company_id={company_id}"
            if escalation_id:
                deep = f"{deep}&escalation={escalation_id}"
            push = deliver_admin_push(
                db,
                str(company_id),
                title[:80],
                message[:160],
                tag=f"camera-{esc}"[:64],
                extra={
                    "url": deep,
                    "kind": "camera_critical",
                    "company_id": str(company_id),
                    "escalation": str(escalation_id or ""),
                },
            )
            result["push"] = int(push.get("sent") or 0) > 0
        except Exception:
            pass
    return result


def _notify_critical_sms_push(
    db,
    company_id: str,
    *,
    title: str,
    message: str,
    escalation_id: str | None,
    event_id: str = "",
) -> dict:
    return _notify_sms_push(
        db,
        company_id,
        title=title,
        message=message,
        escalation_id=escalation_id,
        event_id=event_id,
        send_sms_flag=True,
        send_push_flag=True,
    )


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
    clip_b64: str | None = None,
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

    from .camera_watch import quiet_suppressed_channels, resolve_watch_settings, severity_rank

    after_hours = bool(analysis.get("afterHours"))
    max_sev = str(analysis.get("maxSeverity") or "").lower() or "info"
    critical = bool(analysis.get("critical") or max_sev == "critical")
    channels = {"sms": False, "push": False}
    watch_cfg = resolve_watch_settings(db, str(company_id), site=location)
    notify_rules = watch_cfg.get("notifyRules") if isinstance(watch_cfg.get("notifyRules"), dict) else {}
    sms_min = str(notify_rules.get("sms") or "critical").lower()
    push_min = str(notify_rules.get("push") or "high").lower()
    email_mode = str(notify_rules.get("email") or "immediate").lower()
    send_sms_flag = severity_rank(max_sev) >= severity_rank(sms_min)
    send_push_flag = severity_rank(max_sev) >= severity_rank(push_min)
    # Digest mode: skip immediate email unless critical
    send_email_now = not (email_mode == "digest" and not critical)
    quiet_skip = quiet_suppressed_channels(watch_cfg, severity=max_sev)
    if "sms" in quiet_skip:
        send_sms_flag = False
    if "push" in quiet_skip:
        send_push_flag = False
    if "email" in quiet_skip:
        send_email_now = False
    watch_tag = " [Außerhalb Arbeitszeit / Watch-Mode]" if after_hours else ""
    title = f"Kamera-Alarm{watch_tag}: {camera_name or camera_id}"
    message = (
        f"{created_at}: {camera_name or camera_id} ({location or 'Baustelle'}) — "
        f"{event_type}. {summary}"
        + (" · Verdächtiger Vorfall außerhalb der Betriebszeiten (nicht als Diebstahl bestätigt)." if after_hours else "")
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

    _notify_admin_inbox(
        str(company_id),
        title=title,
        message=message,
        severity="critical" if critical else "high",
    )

    escalation = None
    if critical:
        try:
            from .camera_escalation import create_critical_escalation

            escalation = create_critical_escalation(
                db,
                company_id=str(company_id),
                event_id=event_id,
                camera_id=camera_id,
                camera_name=camera_name,
                location=location,
                event_type=event_type,
                analysis=analysis,
                snapshot_b64=snapshot_b64 or "",
                clip_b64=clip_b64 or "",
                site=location,
            )
        except Exception:
            escalation = None

    if send_sms_flag or send_push_flag:
        channels = _notify_sms_push(
            db,
            str(company_id),
            title=title,
            message=message,
            escalation_id=(escalation or {}).get("id") if isinstance(escalation, dict) else None,
            event_id=event_id,
            send_sms_flag=send_sms_flag,
            send_push_flag=send_push_flag,
        )

    pdf_bytes = None
    emails_sent = 0
    if send_email_now:
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

        subject = f"SUPPIX Kamera-Alarm{watch_tag} — {camera_name or camera_id}"
        police_lines = []
        if escalation and isinstance(escalation, dict):
            police = escalation.get("police") or {}
            station = police.get("station") or {}
            if station:
                police_lines.append(
                    f"Empfohlene Polizeidienststelle: {station.get('name')} · {station.get('address')} · {station.get('phone')}"
                )
            emerg = police.get("countryEmergency") or {}
            if emerg.get("number"):
                police_lines.append(f"Notruf ({emerg.get('country') or ''}): {emerg.get('number')} ({emerg.get('label')})")
            police_lines.append("Kein automatischer Notruf — menschliche Freigabe erforderlich.")
        text_body = (
            f"{message}\n\n"
            + "\n".join(f"- {line}" for line in alert_lines)
            + ("\n\n" + "\n".join(police_lines) if police_lines else "")
            + "\n\nBitte Live-Ansicht und Ereignisliste in WorkPass prüfen."
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

    return {
        "ok": True,
        "emailsSent": emails_sent,
        "emailSkippedDigest": not send_email_now,
        "eventId": event_id,
        "afterHours": after_hours,
        "critical": critical,
        "escalationId": (escalation or {}).get("id") if isinstance(escalation, dict) else None,
        "police": (escalation or {}).get("police") if isinstance(escalation, dict) else None,
        "smsSent": channels.get("sms"),
        "pushSent": channels.get("push"),
        "quietSuppressed": sorted(quiet_skip),
        "notifyRules": notify_rules,
        "autoDial": False,
    }


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

    subject = f"SUPPIX — Kamera offline ({camera_name or camera_id})"
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
