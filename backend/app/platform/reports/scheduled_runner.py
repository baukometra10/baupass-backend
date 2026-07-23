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
        jobs = []

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
        company_name = str(company["name"] if company else "")
        from backend.app.platform.reports.report_pdf_layout import build_report_filename, resolve_report_branding

        branding = resolve_report_branding(db, company_id)
        if not company_name:
            company_name = str(branding.get("companyName") or "WorkPass")
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
                    from backend.app.platform.sector.catalog import sector_terms_for_company

                    terms = sector_terms_for_company(db, company_id, lang="de")
                    snapshot["guidance"] = build_operational_guidance(snapshot, terms=terms)
                    pdf = build_executive_summary_pdf(
                        company_name=company_name,
                        snapshot=snapshot,
                        branding=branding,
                        terms=terms,
                    )
                    filename = build_report_filename(
                        company_name=company_name, report_kind="executive", period=day_key
                    )
                    subject = f"{company_name} — Executive Summary {day_key}"
                else:
                    from backend.app.platform.reports.pdf_reports import build_operations_report_pdf

                    admin = db.execute(
                        "SELECT * FROM users WHERE company_id = ? AND role = 'company-admin' LIMIT 1",
                        (company_id,),
                    ).fetchone()
                    user_dict = row_to_dict(admin) if admin else {"role": "company-admin", "company_id": company_id}
                    snapshot = _operations_snapshot_for_user(db, user_dict)
                    from backend.app.platform.sector.catalog import sector_terms_for_company

                    terms = sector_terms_for_company(db, company_id, lang="de")
                    guidance = build_operational_guidance(snapshot, terms=terms)
                    pdf = build_operations_report_pdf(
                        title="Betriebsbericht",
                        company_name=company_name,
                        snapshot=snapshot,
                        guidance=guidance,
                        branding=branding,
                        terms=terms,
                    )
                    filename = build_report_filename(
                        company_name=company_name, report_kind="betriebsbericht", period=day_key
                    )
                    subject = f"{company_name} — Betriebsbericht {day_key}"

                from backend.app.platform.reports.report_email_template import build_report_meta

                report_meta = build_report_meta(
                    report_title="Executive Summary" if report_type == "executive" else "Betriebsbericht",
                    message=f"Geplanter Bericht ({report_type}) für {company_name}.",
                    company_name=company_name,
                    company_id=company_id,
                    period=day_key,
                    pdf_filename=filename,
                )
                ok, err = send_pdf_report_email(
                    to=email,
                    subject=subject,
                    body_text=f"Geplanter Bericht ({report_type}) für {company_name}.",
                    pdf_bytes=pdf,
                    filename=filename,
                    report_meta=report_meta,
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
