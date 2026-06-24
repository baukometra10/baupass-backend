"""Scheduled daily operations PDF reports per company admin."""
from __future__ import annotations

import os
from typing import Any


def deliver_daily_ops_pdfs(db, *, force: bool = False) -> dict[str, Any]:
    """
    Send one operations PDF per active company to each company-admin with email.
    Skips companies already dispatched today (audit log dedup, local company date).
    By default only sends during the local 08:00 window (see schedule.py).
    """
    from backend.app.platform.reports.datev_attachment import build_datev_csv_attachment
    from backend.app.platform.reports.email_delivery import send_pdf_report_email
    from backend.app.platform.reports.guidance import build_operational_guidance
    from backend.app.platform.reports.pdf_reports import build_operations_report_pdf
    from backend.app.platform.reports.schedule import (
        is_daily_report_send_window,
        local_day_key,
        resolve_company_timezone,
    )
    from backend.server import _operations_snapshot_for_user, log_audit, now_iso

    if str(os.getenv("BAUPASS_DAILY_OPS_PDF", "1")).strip().lower() in {"0", "false", "off", "no"}:
        return {"ok": True, "skipped": True, "reason": "BAUPASS_DAILY_OPS_PDF disabled"}

    attach_datev = str(os.getenv("BAUPASS_DAILY_ATTACH_DATEV_CSV", "1")).strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }

    companies = db.execute(
        "SELECT id, name FROM companies WHERE deleted_at IS NULL AND status != 'gesperrt'"
    ).fetchall()
    sent = 0
    skipped = 0
    waiting_tz = 0
    errors: list[str] = []

    for company in companies:
        company_id = str(company["id"])
        tz_name = resolve_company_timezone(db, company_id)
        local_day = local_day_key(tz_name)

        if not force and not is_daily_report_send_window(tz_name):
            waiting_tz += 1
            continue

        dedup_key = f"daily-{local_day}"
        already = db.execute(
            """
            SELECT id FROM audit_logs
            WHERE event_type = 'reporting.daily_pdf_sent'
              AND company_id = ?
              AND target_id = ?
            LIMIT 1
            """,
            (company_id, dedup_key),
        ).fetchone()
        if already:
            skipped += 1
            continue

        admins = db.execute(
            """
            SELECT id, email, username
            FROM users
            WHERE company_id = ?
              AND role = 'company-admin'
              AND COALESCE(email, '') != ''
            """,
            (company_id,),
        ).fetchall()
        if not admins:
            skipped += 1
            continue

        fake_user = {"role": "company-admin", "company_id": company_id, "email": ""}
        snapshot = _operations_snapshot_for_user(db, fake_user)
        snapshot["companyName"] = str(company["name"] or "")
        guidance = build_operational_guidance(snapshot)
        pdf_bytes = build_operations_report_pdf(
            title="SUPPIX Daily Operations Report",
            company_name=str(company["name"] or "SUPPIX"),
            snapshot=snapshot,
            guidance=guidance,
        )
        period = local_day
        filename = f"baupass-daily-{company_id}-{period}.pdf"
        extra_attachments: list[dict[str, Any]] = []
        if attach_datev:
            datev_att = build_datev_csv_attachment(db, company_id, period=now_iso()[:7])
            if datev_att:
                extra_attachments.append(datev_att)

        company_sent = 0
        for admin in admins:
            recipient = str(admin["email"] or "").strip()
            if not recipient or "@" not in recipient:
                continue
            subject = f"SUPPIX Tagesbericht {period} — {company['name']}"
            body = (
                f"Guten Tag,\n\n"
                f"anbei der automatische Tagesbericht (PDF) für {company['name']}.\n"
                f"Enthalten sind Live-KPIs, Zutritte, Lohn/Compliance und empfohlene Maßnahmen.\n"
            )
            if extra_attachments:
                body += "Zusätzlich: DATEV-Lohn-CSV für den aktuellen Monat.\n"
            body += "\nSUPPIX / Auto-Report"

            ok, err = send_pdf_report_email(
                to=recipient,
                subject=subject,
                body_text=body,
                pdf_bytes=pdf_bytes,
                filename=filename,
                extra_attachments=extra_attachments,
            )
            if ok:
                company_sent += 1
                sent += 1
            else:
                errors.append(f"{company_id}:{recipient}:{err}")

        if company_sent > 0:
            log_audit(
                "reporting.daily_pdf_sent",
                f"Tages-PDF ({local_day} {tz_name}) an {company_sent} Admin(s) für {company['name']}",
                target_type="company",
                target_id=dedup_key,
                company_id=company_id,
            )
            db.commit()
        else:
            skipped += 1

    return {
        "ok": True,
        "sent": sent,
        "skipped": skipped,
        "waitingTimezoneWindow": waiting_tz,
        "forced": bool(force),
        "errors": errors[:20],
    }
