"""Company-wide monthly Einsatzplan batch — draft, confirm, send."""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime, timezone
from typing import Any

from .deployment_store import build_month_calendar, list_deployment_days, upsert_deployment_days


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _table_exists(db) -> bool:
    try:
        db.execute("SELECT 1 FROM deployment_month_batches LIMIT 1")
        return True
    except Exception:
        return False


def _next_year_month(year: int, month: int) -> tuple[int, int]:
    if month >= 12:
        return year + 1, 1
    return year, month + 1


def _prev_year_month(year: int, month: int) -> tuple[int, int]:
    if month <= 1:
        return year - 1, 12
    return year, month - 1


def get_month_batch(db, company_id: str, year: int, month: int) -> dict[str, Any]:
    if not _table_exists(db):
        return {"status": "draft", "exists": False}
    row = db.execute(
        """
        SELECT status, prepared_at, prepared_source, confirmed_by, confirmed_at,
               sent_at, last_edited_at, send_summary_json, awaiting_confirm
        FROM deployment_month_batches
        WHERE company_id = ? AND year = ? AND month = ?
        """,
        (str(company_id), int(year), int(month)),
    ).fetchone()
    if not row:
        return {"status": "draft", "exists": False}
    summary = {}
    try:
        summary = json.loads(row["send_summary_json"] or "{}")
    except json.JSONDecodeError:
        pass
    return {
        "status": row["status"] or "draft",
        "exists": True,
        "preparedAt": row["prepared_at"],
        "preparedSource": row["prepared_source"],
        "confirmedBy": row["confirmed_by"],
        "confirmedAt": row["confirmed_at"],
        "sentAt": row["sent_at"],
        "lastEditedAt": row["last_edited_at"],
        "awaitingConfirm": bool(row["awaiting_confirm"]),
        "sendSummary": summary,
    }


def _upsert_batch(
    db,
    *,
    company_id: str,
    year: int,
    month: int,
    status: str | None = None,
    prepared_source: str | None = None,
    awaiting_confirm: bool | None = None,
    confirmed_by: str | None = None,
    confirmed_at: str | None = None,
    sent_at: str | None = None,
    send_summary: dict | None = None,
    touch_edited: bool = False,
) -> None:
    existing = get_month_batch(db, company_id, year, month)
    now = _now_iso()
    st = status if status is not None else (existing.get("status") if existing.get("exists") else "draft")
    ac = (
        awaiting_confirm
        if awaiting_confirm is not None
        else bool(existing.get("awaitingConfirm")) if existing.get("exists") else False
    )
    prep_at = existing.get("preparedAt") if existing.get("exists") else None
    prep_src = existing.get("preparedSource") if existing.get("exists") else None
    if prepared_source:
        prep_at = now
        prep_src = prepared_source
    edited = now if touch_edited else (existing.get("lastEditedAt") if existing.get("exists") else None)
    summary_json = (
        json.dumps(send_summary)
        if send_summary is not None
        else (json.dumps(existing.get("sendSummary") or {}) if existing.get("exists") else "{}")
    )
    db.execute(
        """
        INSERT INTO deployment_month_batches
            (company_id, year, month, status, prepared_at, prepared_source,
             confirmed_by, confirmed_at, sent_at, last_edited_at, send_summary_json, awaiting_confirm)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id, year, month) DO UPDATE SET
            status = excluded.status,
            prepared_at = excluded.prepared_at,
            prepared_source = excluded.prepared_source,
            confirmed_by = excluded.confirmed_by,
            confirmed_at = excluded.confirmed_at,
            sent_at = excluded.sent_at,
            last_edited_at = excluded.last_edited_at,
            send_summary_json = excluded.send_summary_json,
            awaiting_confirm = excluded.awaiting_confirm
        """,
        (
            str(company_id),
            int(year),
            int(month),
            st,
            prep_at,
            prep_src,
            confirmed_by if confirmed_by is not None else (existing.get("confirmedBy") if existing.get("exists") else None),
            confirmed_at if confirmed_at is not None else (existing.get("confirmedAt") if existing.get("exists") else None),
            sent_at if sent_at is not None else (existing.get("sentAt") if existing.get("exists") else None),
            edited,
            summary_json,
            1 if ac else 0,
        ),
    )
    db.commit()


def mark_month_edited(db, company_id: str, year: int, month: int) -> None:
    """Any edit reopens a sent month for correction (status → draft)."""
    if not _table_exists(db):
        return
    batch = get_month_batch(db, company_id, year, month)
    if not batch.get("exists"):
        _upsert_batch(db, company_id=company_id, year=year, month=month, status="draft", touch_edited=True)
        return
    new_status = "draft" if batch.get("status") == "sent" else (batch.get("status") or "draft")
    _upsert_batch(
        db,
        company_id=company_id,
        year=year,
        month=month,
        status=new_status,
        awaiting_confirm=new_status != "sent",
        touch_edited=True,
    )


def worker_month_summary(db, company_id: str, year: int, month: int) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT id, first_name, last_name, badge_id
        FROM workers
        WHERE company_id = ? AND deleted_at IS NULL
          AND COALESCE(status, 'aktiv') NOT IN ('gesperrt', 'inactive', 'deleted')
        ORDER BY last_name, first_name
        LIMIT 300
        """,
        (str(company_id),),
    ).fetchall()
    from .deployment_responses import (
        attach_responses_to_days,
        count_declined_days,
        list_responses_for_month,
    )
    from .deployment_store import build_month_calendar

    out = []
    for w in rows:
        wid = str(w["id"])
        days = list_deployment_days(db, company_id=company_id, worker_id=wid, year=year, month=month)
        filled = sum(1 for d in days if str(d.get("location_label") or "").strip())
        last = calendar.monthrange(year, month)[1]
        cal_days = build_month_calendar(
            db, company_id=company_id, worker_id=wid, year=year, month=month, lang="de"
        )
        responses = list_responses_for_month(
            db, company_id=company_id, worker_id=wid, year=year, month=month
        )
        cal_days = attach_responses_to_days(cal_days, responses)
        declined_count = count_declined_days(cal_days)
        out.append(
            {
                "workerId": wid,
                "name": f"{w['first_name']} {w['last_name']}".strip(),
                "badgeId": w["badge_id"],
                "daysFilled": filled,
                "daysInMonth": last,
                "declinedDayCount": declined_count,
                "hasDeclines": declined_count > 0,
                "ready": filled >= max(1, int(last * 0.5)),
            }
        )
    return out


def copy_month_weekday_pattern(
    db,
    *,
    company_id: str,
    source_year: int,
    source_month: int,
    target_year: int,
    target_month: int,
    skip_weekends: bool = True,
) -> dict[str, Any]:
    """Copy each worker's weekday→location pattern from source month into target month."""
    workers = db.execute(
        """
        SELECT id FROM workers
        WHERE company_id = ? AND deleted_at IS NULL
          AND COALESCE(status, 'aktiv') NOT IN ('gesperrt', 'inactive', 'deleted')
        """,
        (str(company_id),),
    ).fetchall()
    workers_touched = 0
    days_written = 0
    for w in workers:
        wid = str(w["id"])
        prev = list_deployment_days(
            db, company_id=company_id, worker_id=wid, year=source_year, month=source_month
        )
        if not prev:
            continue
        by_weekday: dict[int, str] = {}
        for row in prev:
            loc = str(row.get("location_label") or "").strip()
            if not loc:
                continue
            try:
                d = date.fromisoformat(str(row["work_date"])[:10])
                by_weekday[d.weekday()] = loc
            except ValueError:
                continue
        if not by_weekday:
            continue
        last = calendar.monthrange(target_year, target_month)[1]
        days_payload = []
        for day_num in range(1, last + 1):
            d = date(target_year, target_month, day_num)
            if skip_weekends and d.weekday() >= 5:
                continue
            loc = by_weekday.get(d.weekday())
            if not loc:
                continue
            days_payload.append({"date": d.isoformat(), "location": loc, "notes": ""})
        if days_payload:
            upsert_deployment_days(
                db,
                company_id=company_id,
                worker_id=wid,
                days=days_payload,
                source="month_copy",
            )
            workers_touched += 1
            days_written += len(days_payload)
    _upsert_batch(
        db,
        company_id=company_id,
        year=target_year,
        month=target_month,
        status="draft",
        prepared_source=f"copy_from_{source_year}_{source_month:02d}",
        awaiting_confirm=True,
    )
    return {
        "ok": True,
        "sourceYear": source_year,
        "sourceMonth": source_month,
        "targetYear": target_year,
        "targetMonth": target_month,
        "workersTouched": workers_touched,
        "daysWritten": days_written,
    }


def prepare_next_month_draft(db, company_id: str, *, reference: date | None = None) -> dict[str, Any]:
    """Prepare next calendar month from current/previous pattern; never sends."""
    ref = reference or datetime.now(timezone.utc).date()
    ty, tm = _next_year_month(ref.year, ref.month)
    sy, sm = ref.year, ref.month
    batch = get_month_batch(db, company_id, ty, tm)
    if batch.get("exists") and batch.get("status") == "sent":
        return {"ok": False, "error": "target_month_already_sent", "year": ty, "month": tm}
    result = copy_month_weekday_pattern(
        db,
        company_id=company_id,
        source_year=sy,
        source_month=sm,
        target_year=ty,
        target_month=tm,
    )
    _upsert_batch(
        db,
        company_id=company_id,
        year=ty,
        month=tm,
        prepared_source="autopilot_next_month",
        awaiting_confirm=True,
    )
    try:
        from backend.server import create_system_alert

        create_system_alert(
            db,
            code="deployment_month_awaiting_confirm",
            severity="info",
            message=f"Einsatzplan {tm:02d}/{ty} wurde als Entwurf vorbereitet — bitte prüfen und Versand bestätigen.",
            details=json.dumps({"companyId": company_id, "year": ty, "month": tm}),
            dedup_minutes=60 * 24 * 7,
        )
        db.commit()
    except Exception:
        pass
    result["awaitingConfirm"] = True
    result["year"] = ty
    result["month"] = tm
    return result


def send_worker_plan(
    db,
    *,
    company_id: str,
    worker_id: str,
    year: int,
    month: int,
    lang: str = "de",
) -> dict[str, Any]:
    from .deployment_pdf import build_deployment_plan_pdf
    from backend.app.platform.reports.email_delivery import send_pdf_report_email

    w = db.execute(
        """
        SELECT id, first_name, last_name, badge_id, contact_email
        FROM workers WHERE id = ? AND company_id = ?
        """,
        (str(worker_id), str(company_id)),
    ).fetchone()
    if not w:
        return {"ok": False, "error": "worker_not_found", "workerId": worker_id}
    days = build_month_calendar(db, company_id=company_id, worker_id=worker_id, year=year, month=month, lang=lang)
    if not any(str(d.get("location") or "").strip() for d in days):
        return {"ok": False, "error": "no_locations", "workerId": worker_id}
    from .deployment_branding import resolve_company_pdf_branding

    branding = resolve_company_pdf_branding(db, str(company_id))
    pdf_bytes = build_deployment_plan_pdf(
        company_name=branding.get("companyName") or "WorkPass",
        worker_name=f"{w['first_name']} {w['last_name']}".strip(),
        badge_id=w["badge_id"],
        year=year,
        month=month,
        days=days,
        lang=lang,
        plan_tier="professional",
        branding=branding,
    )
    to_email = str(w["contact_email"] or "").strip()
    ok, err = False, "no_email"
    if to_email:
        ok, err = send_pdf_report_email(
            to=to_email,
            subject=f"Einsatzplan {month:02d}/{year} — {company['name'] if company else 'SUPPIX'}",
            body_text=f"Ihr Einsatzplan für {month:02d}/{year} ist im Anhang (PDF).",
            pdf_bytes=pdf_bytes,
            filename=f"einsatzplan-{year}-{month:02d}.pdf",
        )
    document_id = None
    try:
        from .deployment_worker import persist_worker_deployment_pdf

        document_id = persist_worker_deployment_pdf(
            db,
            company_id=str(company_id),
            worker_id=str(worker_id),
            year=year,
            month=month,
            pdf_bytes=pdf_bytes,
            lang=lang,
        )
    except Exception:
        pass

    sent_ok = ok or bool(document_id)
    if sent_ok:
        try:
            from .deployment_responses import clear_worker_declines_for_month

            clear_worker_declines_for_month(
                db,
                company_id=str(company_id),
                worker_id=str(worker_id),
                year=year,
                month=month,
            )
        except Exception:
            pass

    return {
        "ok": sent_ok,
        "workerId": worker_id,
        "email": to_email or None,
        "emailSent": ok,
        "emailError": err,
        "pushSent": 1 if document_id else 0,
        "documentId": document_id,
    }


def confirm_and_send_month(
    db,
    *,
    company_id: str,
    year: int,
    month: int,
    user_id: str,
    user_confirmed: bool,
    lang: str = "de",
    worker_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Send only when user_confirmed is True (explicit admin confirmation)."""
    if not user_confirmed:
        return {"ok": False, "error": "user_confirmation_required"}

    batch = get_month_batch(db, company_id, year, month)
    if batch.get("status") == "sent" and not batch.get("awaitingConfirm"):
        return {"ok": False, "error": "already_sent", "sentAt": batch.get("sentAt")}

    summaries = worker_month_summary(db, company_id, year, month)
    targets = summaries
    if worker_ids:
        wanted = {str(x) for x in worker_ids}
        targets = [s for s in summaries if s["workerId"] in wanted]

    sent = 0
    failed = 0
    details: list[dict] = []
    for row in targets:
        if not row.get("ready") and not worker_ids:
            continue
        res = send_worker_plan(
            db,
            company_id=company_id,
            worker_id=row["workerId"],
            year=year,
            month=month,
            lang=lang,
        )
        details.append(res)
        if res.get("ok"):
            sent += 1
        else:
            failed += 1

    if sent == 0:
        return {
            "ok": False,
            "error": "no_workers_sent",
            "failed": failed,
            "details": details[:20],
        }

    now = _now_iso()
    summary = {"sent": sent, "failed": failed, "at": now}
    _upsert_batch(
        db,
        company_id=company_id,
        year=year,
        month=month,
        status="sent",
        confirmed_by=user_id,
        confirmed_at=now,
        sent_at=now,
        awaiting_confirm=False,
        send_summary=summary,
    )
    try:
        from backend.server import log_audit

        log_audit(
            "deployment.month_sent",
            f"Einsatzplan {month:02d}/{year} an {sent} Mitarbeiter versendet (bestätigt).",
            company_id=str(company_id),
            target_type="deployment_month",
            target_id=f"{year}-{month:02d}",
        )
    except Exception:
        pass
    return {"ok": True, "sent": sent, "failed": failed, "confirmedAt": now, "details": details[:30]}


def reopen_month(db, company_id: str, year: int, month: int) -> dict[str, Any]:
    _upsert_batch(
        db,
        company_id=company_id,
        year=year,
        month=month,
        status="draft",
        awaiting_confirm=True,
    )
    return {"ok": True, "status": "draft", "year": year, "month": month}
