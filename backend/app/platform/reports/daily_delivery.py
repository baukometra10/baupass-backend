"""Scheduled daily operations PDF reports per company admin."""
from __future__ import annotations

import os
from typing import Any


def deliver_daily_ops_pdfs(db) -> dict[str, Any]:
    """
    Send one operations PDF per active company to each company-admin with email.
    Skips companies already dispatched today (audit log dedup).
    """
    from backend.app.platform.reports.email_delivery import send_pdf_report_email
    from backend.app.platform.reports.guidance import build_operational_guidance
    from backend.app.platform.reports.pdf_reports import build_operations_report_pdf
    from backend.server import _operations_snapshot_for_user, log_audit, now_iso

    if str(os.getenv("BAUPASS_DAILY_OPS_PDF", "1")).strip().lower() in {"0", "false", "off", "no"}:
        return {"ok": True, "skipped": True, "reason": "BAUPASS_DAILY_OPS_PDF disabled"}

    today_prefix = now_iso()[:10]
    companies = db.execute(
        "SELECT id, name FROM companies WHERE deleted_at IS NULL AND status != 'gesperrt'"
    ).fetchall()
    sent = 0
    skipped = 0
    errors: list[str] = []

    for company in companies:
        company_id = str(company["id"])
        already = db.execute(
            """
            SELECT id FROM audit_logs
            WHERE event_type = 'reporting.daily_pdf_sent'
              AND company_id = ?
              AND created_at LIKE ?
            LIMIT 1
            """,
            (company_id, f"{today_prefix}%"),
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
            title="BauPass Daily Operations Report",
            company_name=str(company["name"] or "BauPass"),
            snapshot=snapshot,
            guidance=guidance,
        )
        period = today_prefix
        filename = f"baupass-daily-{company_id}-{period}.pdf"
        company_sent = 0

        for admin in admins:
            recipient = str(admin["email"] or "").strip()
            if not recipient or "@" not in recipient:
                continue
            subject = f"BauPass Tagesbericht {period} — {company['name']}"
            body = (
                f"Guten Tag,\n\n"
                f"anbei der automatische Tagesbericht (PDF) für {company['name']}.\n"
                f"Enthalten sind Live-KPIs, Zutritte der letzten 7 Tage und empfohlene Maßnahmen.\n\n"
                f"BauPass / Auto-Report"
            )
            ok, err = send_pdf_report_email(
                to=recipient,
                subject=subject,
                body_text=body,
                pdf_bytes=pdf_bytes,
                filename=filename,
            )
            if ok:
                company_sent += 1
                sent += 1
            else:
                errors.append(f"{company_id}:{recipient}:{err}")

        if company_sent > 0:
            log_audit(
                "reporting.daily_pdf_sent",
                f"Tages-PDF an {company_sent} Admin(s) für {company['name']}",
                target_type="company",
                target_id=company_id,
                company_id=company_id,
            )
            db.commit()
        else:
            skipped += 1

    return {"ok": True, "sent": sent, "skipped": skipped, "errors": errors[:20]}
