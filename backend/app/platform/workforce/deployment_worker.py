"""Worker-facing Einsatzplan: persist PDF, in-app notifications, API payloads."""
from __future__ import annotations

import secrets
from datetime import date
from typing import Any

from .deployment_month import get_month_batch
from .deployment_store import build_month_calendar


def month_plan_published(db, company_id: str, year: int, month: int) -> bool:
    batch = get_month_batch(db, str(company_id), int(year), int(month))
    return str(batch.get("status") or "").lower() == "sent"


def worker_has_distributed_plan(db, worker_id: str, year: int, month: int) -> bool:
    """True after admin «An MA senden» (PDF + Mitteilung), even if month batch is still draft."""
    marker = _deployment_doc_marker(year, month)
    try:
        row = db.execute(
            """
            SELECT 1 FROM worker_documents
            WHERE worker_id = ? AND doc_type = 'einsatzplan' AND notes = ?
            LIMIT 1
            """,
            (str(worker_id), marker),
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def worker_month_has_assignments(
    db, *, company_id: str, worker_id: str, year: int, month: int, lang: str = "de"
) -> bool:
    days = build_month_calendar(
        db, company_id=str(company_id), worker_id=str(worker_id), year=year, month=month, lang=lang
    )
    return any(str(d.get("location") or "").strip() for d in days)


def worker_month_published_for_worker(
    db, *, company_id: str, worker_id: str, year: int, month: int
) -> bool:
    if month_plan_published(db, str(company_id), year, month):
        return True
    return worker_has_distributed_plan(db, str(worker_id), year, month)


def worker_can_respond_to_deployment_month(
    db, *, company_id: str, worker_id: str, year: int, month: int, lang: str = "de"
) -> bool:
    """Allow decline/undo when the month was sent to the worker or has saved assignments."""
    if worker_month_published_for_worker(
        db, company_id=str(company_id), worker_id=str(worker_id), year=year, month=month
    ):
        return True
    return worker_month_has_assignments(
        db,
        company_id=str(company_id),
        worker_id=str(worker_id),
        year=year,
        month=month,
        lang=lang,
    )


def list_worker_plan_months(
    db, *, company_id: str, worker_id: str, limit: int = 18
) -> list[dict[str, Any]]:
    """Months visible in the worker app: company-wide send, per-worker send, or saved assignments."""
    seen: set[tuple[int, int]] = set()
    out: list[dict[str, Any]] = []

    def _add(year: int, month: int, sent_at: str | None = None) -> None:
        key = (int(year), int(month))
        if key in seen:
            return
        seen.add(key)
        out.append({"year": key[0], "month": key[1], "sentAt": sent_at})

    for item in list_published_months(db, str(company_id), limit=limit):
        _add(int(item["year"]), int(item["month"]), item.get("sentAt"))

    try:
        rows = db.execute(
            """
            SELECT DISTINCT CAST(substr(notes, 12, 4) AS INTEGER) AS y,
                   CAST(substr(notes, 17, 2) AS INTEGER) AS m,
                   MAX(created_at) AS sent_at
            FROM worker_documents
            WHERE worker_id = ? AND company_id = ? AND doc_type = 'einsatzplan'
              AND notes LIKE 'deployment:____-__'
            GROUP BY y, m
            ORDER BY y DESC, m DESC
            LIMIT ?
            """,
            (str(worker_id), str(company_id), int(limit)),
        ).fetchall()
        for row in rows:
            if row["y"] and row["m"]:
                _add(int(row["y"]), int(row["m"]), row["sent_at"])
    except Exception:
        pass

    try:
        rows = db.execute(
            """
            SELECT DISTINCT CAST(substr(work_date, 1, 4) AS INTEGER) AS y,
                   CAST(substr(work_date, 6, 2) AS INTEGER) AS m
            FROM worker_deployment_days
            WHERE company_id = ? AND worker_id = ? AND location_label != ''
            ORDER BY y DESC, m DESC
            LIMIT ?
            """,
            (str(company_id), str(worker_id), int(limit)),
        ).fetchall()
        for row in rows:
            if row["y"] and row["m"]:
                _add(int(row["y"]), int(row["m"]))
    except Exception:
        pass

    out.sort(key=lambda x: (x["year"], x["month"]), reverse=True)
    return out[: int(limit)]


def list_published_months(db, company_id: str, *, limit: int = 18) -> list[dict[str, Any]]:
    try:
        rows = db.execute(
            """
            SELECT year, month, sent_at
            FROM deployment_month_batches
            WHERE company_id = ? AND status = 'sent'
            ORDER BY year DESC, month DESC
            LIMIT ?
            """,
            (str(company_id), int(limit)),
        ).fetchall()
    except Exception:
        return []
    return [
        {"year": int(r["year"]), "month": int(r["month"]), "sentAt": r["sent_at"]}
        for r in rows
    ]


def _deployment_doc_marker(year: int, month: int) -> str:
    return f"deployment:{year:04d}-{month:02d}"


def persist_worker_deployment_pdf(
    db,
    *,
    company_id: str,
    worker_id: str,
    year: int,
    month: int,
    pdf_bytes: bytes,
    lang: str = "de",
) -> str | None:
    """Store monthly Einsatzplan PDF in worker_documents (replaces prior month copy)."""
    from backend.app.platform.notifications.worker_mitteilung import notify_worker_deployment_plan
    from backend.server import DOCS_UPLOAD_DIR, _stored_file_path, now_iso

    marker = _deployment_doc_marker(year, month)
    old_rows = db.execute(
        """
        SELECT id, file_path FROM worker_documents
        WHERE worker_id = ? AND doc_type = 'einsatzplan' AND notes = ?
        """,
        (str(worker_id), marker),
    ).fetchall()
    for row in old_rows:
        try:
            from backend.server import BASE_DIR

            fp = BASE_DIR / str(row["file_path"] or "")
            if fp.is_file():
                fp.unlink()
        except Exception:
            pass
        db.execute("DELETE FROM worker_documents WHERE id = ?", (row["id"],))

    worker_doc_dir = (DOCS_UPLOAD_DIR / str(worker_id)).resolve()
    worker_doc_dir.mkdir(parents=True, exist_ok=True)
    filename = f"einsatzplan-{year:04d}-{month:02d}.pdf"
    file_path = (worker_doc_dir / filename).resolve()
    file_path.write_bytes(pdf_bytes)
    stored_path = _stored_file_path(file_path)
    doc_id = f"doc-{secrets.token_hex(8)}"
    month_label = f"{month:02d}/{year}"
    db.execute(
        """
        INSERT INTO worker_documents
            (id, worker_id, company_id, doc_type, filename, file_path, file_size,
             source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            doc_id,
            str(worker_id),
            str(company_id),
            "einsatzplan",
            filename,
            stored_path,
            len(pdf_bytes),
            "",
            None,
            None,
            now_iso(),
            marker,
        ),
    )
    notify_worker_deployment_plan(db, str(worker_id), year=int(year), month=int(month))
    return doc_id


def worker_deployment_plan_payload(
    db,
    *,
    worker: Any,
    year: int,
    month: int,
    lang: str = "de",
) -> dict[str, Any]:
    company_id = str(worker["company_id"])
    worker_id = str(worker["id"])
    company_published = month_plan_published(db, company_id, year, month)
    worker_published = worker_month_published_for_worker(
        db, company_id=company_id, worker_id=worker_id, year=year, month=month
    )
    published = worker_published
    can_respond = worker_can_respond_to_deployment_month(
        db,
        company_id=company_id,
        worker_id=worker_id,
        year=year,
        month=month,
        lang=lang,
    )
    from .deployment_responses import attach_responses_to_days, count_declined_days, list_responses_for_month

    days = build_month_calendar(
        db, company_id=company_id, worker_id=worker_id, year=year, month=month, lang=lang
    )
    responses = list_responses_for_month(db, company_id=company_id, worker_id=worker_id, year=year, month=month)
    days = attach_responses_to_days(days, responses)
    scheduled = [d for d in days if str(d.get("location") or "").strip()]
    has_assignments = bool(scheduled)
    visible = published or has_assignments
    months = list_worker_plan_months(db, company_id=company_id, worker_id=worker_id)
    if not visible:
        return {
            "ok": True,
            "published": False,
            "canRespond": False,
            "companyPublished": company_published,
            "visible": False,
            "error": "no_plan",
            "year": year,
            "month": month,
            "days": days,
            "scheduledDayCount": 0,
            "declinedDayCount": 0,
            "months": months,
            "companyName": _company_name(db, company_id),
            "workerName": f"{worker['first_name']} {worker['last_name']}".strip(),
        }
    declined_count = count_declined_days(days)
    batch = get_month_batch(db, company_id, year, month)
    doc = db.execute(
        """
        SELECT id, filename, created_at FROM worker_documents
        WHERE worker_id = ? AND doc_type = 'einsatzplan' AND notes = ?
        ORDER BY created_at DESC LIMIT 1
        """,
        (worker_id, _deployment_doc_marker(year, month)),
    ).fetchone()
    sent_at = batch.get("sentAt") if company_published else None
    if not sent_at and doc:
        sent_at = doc["created_at"]
    return {
        "ok": True,
        "published": published,
        "canRespond": can_respond,
        "companyPublished": company_published,
        "visible": True,
        "year": year,
        "month": month,
        "sentAt": sent_at,
        "days": days,
        "scheduledDayCount": len(scheduled),
        "declinedDayCount": declined_count,
        "documentId": doc["id"] if doc else None,
        "months": months,
        "companyName": _company_name(db, company_id),
        "workerName": f"{worker['first_name']} {worker['last_name']}".strip(),
    }


def build_worker_deployment_pdf_bytes(
    db,
    *,
    worker: Any,
    year: int,
    month: int,
    lang: str = "de",
) -> bytes | None:
    from .deployment_pdf import build_deployment_plan_pdf

    company_id = str(worker["company_id"])
    worker_id = str(worker["id"])
    if not worker_month_published_for_worker(
        db, company_id=company_id, worker_id=worker_id, year=year, month=month
    ):
        return None
    days = build_month_calendar(
        db, company_id=company_id, worker_id=str(worker["id"]), year=year, month=month, lang=lang
    )
    if not any(str(d.get("location") or "").strip() for d in days):
        return None
    from .deployment_branding import resolve_company_pdf_branding

    branding = resolve_company_pdf_branding(db, str(company_id))
    return build_deployment_plan_pdf(
        company_name=branding.get("companyName") or "WorkPass",
        worker_name=f"{worker['first_name']} {worker['last_name']}".strip(),
        badge_id=worker["badge_id"],
        year=year,
        month=month,
        days=days,
        lang=lang,
        plan_tier="professional",
        branding=branding,
    )


def _company_name(db, company_id: str) -> str:
    row = db.execute("SELECT name FROM companies WHERE id = ?", (company_id,)).fetchone()
    return str(row["name"] if row else "")
