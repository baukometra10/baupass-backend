"""Run per-company scheduled report jobs (Phase B)."""
from __future__ import annotations

import json
from typing import Any


def run_scheduled_reports(db, *, force: bool = False) -> dict[str, Any]:
    from backend.app.platform.reports.daily_delivery import deliver_daily_ops_pdfs
    from backend.app.platform.reports.email_delivery import send_pdf_report_email
    from backend.app.platform.reports.executive_report import build_executive_summary_pdf
    from backend.app.platform.reports.guidance import build_operational_guidance
    from backend.app.platform.reports.schedule import local_day_key, local_now_for_timezone
    from backend.server import _operations_snapshot_for_user, log_audit, now_iso, row_to_dict

    try:
        jobs = db.execute(
            "SELECT * FROM scheduled_report_jobs WHERE enabled = 1"
        ).fetchall()
    except Exception:
        return {"ok": True, "skipped": True, "reason": "no_scheduled_report_jobs_table"}

    if not jobs:
        return deliver_daily_ops_pdfs(db, force=force)

    sent = 0
    errors: list[str] = []

    for job in jobs:
        company_id = str(job["company_id"])
        tz = str(job["timezone"] or "Europe/Berlin")
        local = local_now_for_timezone(tz)
        if not force and int(local.hour) != int(job["local_hour"]):
            continue
        day_key = local_day_key(tz)
        if str(job["last_sent_day"] or "") == day_key and not force:
            continue

        recipients = []
        try:
            recipients = json.loads(job["recipients_json"] or "[]")
        except json.JSONDecodeError:
            recipients = []
        if not recipients:
            admins = db.execute(
                "SELECT email FROM users WHERE company_id = ? AND role = 'company-admin' AND COALESCE(email,'') != ''",
                (company_id,),
            ).fetchall()
            recipients = [r["email"] for r in admins]

        company = db.execute("SELECT name FROM companies WHERE id = ?", (company_id,)).fetchone()
        company_name = company["name"] if company else "BauPass"
        report_type = str(job["report_type"] or "daily_ops")

        for email in recipients:
            email = str(email or "").strip()
            if not email or "@" not in email:
                continue
            try:
                if report_type == "executive":
                    admin = db.execute(
                        "SELECT * FROM users WHERE company_id = ? AND role = 'company-admin' LIMIT 1",
                        (company_id,),
                    ).fetchone()
                    user_dict = row_to_dict(admin) if admin else {"role": "company-admin", "company_id": company_id}
                    snapshot = _operations_snapshot_for_user(db, user_dict)
                    snapshot["guidance"] = build_operational_guidance(snapshot)
                    pdf = build_executive_summary_pdf(
                        company_name=company_name,
                        snapshot=snapshot,
                    )
                    filename = f"executive-summary-{day_key}.pdf"
                    subject = f"BauPass Executive Summary {day_key}"
                else:
                    from backend.app.platform.reports.pdf_reports import build_operations_report_pdf

                    admin = db.execute(
                        "SELECT * FROM users WHERE company_id = ? AND role = 'company-admin' LIMIT 1",
                        (company_id,),
                    ).fetchone()
                    user_dict = row_to_dict(admin) if admin else {"role": "company-admin", "company_id": company_id}
                    snapshot = _operations_snapshot_for_user(db, user_dict)
                    guidance = build_operational_guidance(snapshot)
                    pdf = build_operations_report_pdf(
                        title="BauPass Operations Report",
                        company_name=company_name,
                        snapshot=snapshot,
                        guidance=guidance,
                    )
                    filename = f"ops-report-{day_key}.pdf"
                    subject = f"BauPass Operations Report {day_key}"

                ok, err = send_pdf_report_email(
                    to=email,
                    subject=subject,
                    body_text=f"Scheduled report ({report_type}) for {company_name}.",
                    pdf_bytes=pdf,
                    filename=filename,
                )
                if not ok:
                    errors.append(f"{company_id}:{email}:{err}")
                else:
                    sent += 1
            except Exception as exc:
                errors.append(f"{company_id}:{email}:{exc}")

        db.execute(
            "UPDATE scheduled_report_jobs SET last_sent_day = ?, updated_at = ? WHERE id = ?",
            (day_key, now_iso(), job["id"]),
        )
        log_audit(
            "reporting.scheduled_sent",
            f"Scheduled {report_type} for {company_id} on {day_key}",
            target_type="company",
            target_id=company_id,
            company_id=company_id,
        )
        db.commit()

    base = deliver_daily_ops_pdfs(db, force=force)
    base["scheduledSent"] = sent
    base["scheduledErrors"] = errors[:20]
    return base
