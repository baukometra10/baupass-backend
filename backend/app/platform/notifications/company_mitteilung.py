"""Notify company admins (inbox, system alert, e-mail) about worker events."""
from __future__ import annotations

import html
import json
from typing import Any


def _company_admin_recipients(db, company_id: str) -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()
    try:
        company = db.execute(
            "SELECT billing_email FROM companies WHERE id = ?",
            (str(company_id),),
        ).fetchone()
        if company:
            billing = str(company["billing_email"] or "").strip()
            if billing and "@" in billing and billing.lower() not in seen:
                seen.add(billing.lower())
                emails.append(billing)
    except Exception:
        pass
    try:
        rows = db.execute(
            """
            SELECT email FROM users
            WHERE company_id = ? AND role = 'company-admin'
              AND COALESCE(email, '') <> ''
            """,
            (str(company_id),),
        ).fetchall()
        for row in rows:
            addr = str(row["email"] or "").strip()
            if addr and "@" in addr and addr.lower() not in seen:
                seen.add(addr.lower())
                emails.append(addr)
    except Exception:
        pass
    return emails


def notify_company_deployment_day_declined(
    db,
    *,
    company_id: str,
    worker_id: str,
    worker_name: str,
    work_date: str,
    location: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Alert Betrieb when a worker declines a scheduled deployment day."""
    loc = str(location or "").strip() or "—"
    reason_clean = str(reason or "").strip()
    reason_line = f"\nGrund: {reason_clean}" if reason_clean else ""
    message = (
        f"{worker_name} kann am {work_date} nicht arbeiten "
        f"(Einsatz: {loc}).{reason_line}"
    ).strip()

    alert_id = None
    try:
        from backend.server import create_system_alert

        alert_id = create_system_alert(
            db,
            code="deployment_worker_declined",
            severity="warning",
            message=message[:500],
            details=json.dumps(
                {
                    "companyId": str(company_id),
                    "workerId": str(worker_id),
                    "workDate": work_date,
                    "location": loc,
                    "reason": reason_clean,
                },
                ensure_ascii=False,
            ),
            dedup_minutes=5,
        )
    except Exception:
        pass

    try:
        from backend.app.platform.inbox.events import notify_inbox_changed

        notify_inbox_changed(
            str(company_id),
            source="deployment_decline",
            alert_title="Einsatz abgelehnt",
            alert_message=message[:240],
            severity="warning",
        )
    except Exception:
        pass

    try:
        from backend.app.platform.workforce.deployment_month import mark_month_edited

        parts = str(work_date)[:10].split("-")
        if len(parts) >= 2:
            mark_month_edited(db, str(company_id), int(parts[0]), int(parts[1]))
    except Exception:
        pass

    emails_sent = 0
    recipients = _company_admin_recipients(db, company_id)
    if recipients:
        try:
            from backend.app.core.platform_env import default_noreply_email
            from backend.server import _send_via_any_api, get_public_base_url

            settings = db.execute("SELECT smtp_sender_email, smtp_sender_name FROM settings WHERE id = 1").fetchone()
            sender_email = (settings["smtp_sender_email"] if settings else "") or default_noreply_email()
            sender_name = (settings["smtp_sender_name"] if settings else "") or "WorkPass"
            base = get_public_base_url().rstrip("/")
            admin_hint = f"{base}/admin-v2/index.html" if base else ""
            subject = f"WorkPass: Einsatz abgelehnt — {worker_name} ({work_date})"
            text_body = (
                f"{message}\n\n"
                f"Bitte Einsatzplan im Betrieb-Portal prüfen und ggf. anpassen.\n"
                f"{admin_hint}\n"
            )
            msg_safe = html.escape(message).replace("\n", "<br>")
            reason_html = (
                f'<p style="color:#555;"><strong>Grund:</strong> {html.escape(reason_clean)}</p>'
                if reason_clean
                else ""
            )
            html_body = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f4f6f8;margin:0;padding:24px;">
<table width="100%"><tr><td align="center">
<table width="560" style="background:#fff;border-radius:10px;padding:24px;max-width:560px;">
  <tr><td>
    <h2 style="margin:0 0 12px;color:#b45309;">Einsatztag abgelehnt</h2>
    <p style="color:#333;line-height:1.5;">{msg_safe}</p>
    {reason_html}
    <p style="margin-top:20px;color:#666;font-size:13px;">
      Bitte den Monats-Einsatzplan prüfen und bei Bedarf umplanen.
    </p>
  </td></tr>
</table></td></tr></table></body></html>"""
            for recipient in recipients:
                ok, _, _provider = _send_via_any_api(
                    subject,
                    sender_email,
                    sender_name,
                    recipient,
                    text_body,
                    html_body,
                )
                if ok:
                    emails_sent += 1
        except Exception:
            pass

    return {
        "ok": True,
        "alertId": alert_id,
        "emailsSent": emails_sent,
        "recipientCount": len(recipients),
    }
