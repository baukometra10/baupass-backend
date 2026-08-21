"""Access logs, invoices, deployment days, leave requests."""
from __future__ import annotations

from typing import Any

from .base import (
    ApplyContext,
    DomainResult,
    decide_row_action,
    fetch_by_id,
    fingerprint_match,
    g,
    utc_now_iso,
    values_equal,
)


def apply_access_logs(ctx: ApplyContext, rows: list[dict[str, Any]]) -> DomainResult:
    result = DomainResult(domain="access_logs")
    known: set[str] = set()
    try:
        for row in ctx.db.execute("SELECT id FROM workers WHERE company_id = ?", (ctx.company_id,)).fetchall():
            known.add(str(row["id"] if hasattr(row, "keys") else row[0]))
    except Exception:
        pass
    pending: list[tuple] = []
    for item in rows:
        lid = str(g(item, "id", default="")).strip()
        wid = str(g(item, "worker_id", "workerId", default="")).strip()
        if not lid or not wid:
            result.skipped_invalid += 1
            continue
        if wid not in known and not fetch_by_id(ctx.db, "workers", wid):
            result.skipped_invalid += 1
            continue
        existing = fetch_by_id(ctx.db, "access_logs", lid)
        same = bool(existing) and all(
            values_equal(existing.get(k), g(item, k, default=None))
            for k in ("direction", "gate", "note", "timestamp")
        ) and values_equal(existing.get("worker_id"), wid)
        action = decide_row_action(exists=bool(existing), same=same, merge_mode=ctx.merge_mode)
        if action == "unchanged":
            result.unchanged += 1
            continue
        if action == "skip":
            result.conflicts += 1
            result.conflict_ids.append(lid)
            continue
        if action == "fail":
            result.conflicts += 1
            result.conflict_ids.append(lid)
            result.error = f"conflict:access_logs:{lid}"
            return result
        pending.append(
            (
                lid,
                wid,
                str(g(item, "direction", default="check-in") or "check-in"),
                str(g(item, "gate", default="")),
                str(g(item, "note", default="")),
                str(g(item, "timestamp", default=utc_now_iso())),
            )
        )
        result.accepted += 1
    if not ctx.dry_run and pending:
        ctx.db.executemany(
            "INSERT OR REPLACE INTO access_logs (id, worker_id, direction, gate, note, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            pending,
        )
    return result


INVOICE_FIELDS = [
    ("company_id", "companyId"),
    ("invoice_number", "invoiceNumber"),
    ("recipient_email", "recipientEmail"),
    ("total_amount", "totalAmount"),
    ("status",),
]


def apply_invoices(ctx: ApplyContext, rows: list[dict[str, Any]]) -> DomainResult:
    result = DomainResult(domain="invoices")
    pending: list[tuple] = []
    for item in rows:
        iid = str(g(item, "id", default="")).strip()
        cid = str(g(item, "company_id", "companyId", default=ctx.company_id) or ctx.company_id).strip()
        if not iid:
            result.skipped_invalid += 1
            continue
        existing = fetch_by_id(ctx.db, "invoices", iid)
        same = bool(existing) and fingerprint_match(existing, {**item, "company_id": cid}, INVOICE_FIELDS)
        action = decide_row_action(exists=bool(existing), same=same, merge_mode=ctx.merge_mode)
        if action == "unchanged":
            result.unchanged += 1
            continue
        if action == "skip":
            result.conflicts += 1
            result.conflict_ids.append(iid)
            continue
        if action == "fail":
            result.conflicts += 1
            result.conflict_ids.append(iid)
            result.error = f"conflict:invoices:{iid}"
            return result
        pending.append(
            (
                iid,
                str(g(item, "invoice_number", "invoiceNumber", default="")),
                cid,
                str(g(item, "recipient_email", "recipientEmail", default="")),
                str(g(item, "invoice_date", "invoiceDate", default="")),
                str(g(item, "invoice_period", "invoicePeriod", default="")),
                str(g(item, "description", default="")),
                float(g(item, "net_amount", "netAmount", default=0) or 0),
                float(g(item, "vat_rate", "vatRate", default=0) or 0),
                float(g(item, "vat_amount", "vatAmount", default=0) or 0),
                float(g(item, "total_amount", "totalAmount", default=0) or 0),
                str(g(item, "status", default="draft") or "draft"),
                str(g(item, "error_message", "errorMessage", default="")),
                g(item, "sent_at", "sentAt", default=None),
                str(g(item, "rendered_html", "renderedHtml", default="<html><body>Imported</body></html>")),
                ctx.actor_user_id or None,
                str(g(item, "created_at", "createdAt", default=utc_now_iso())),
                g(item, "due_date", "dueDate", default=None),
                g(item, "paid_at", "paidAt", default=None),
                g(item, "auto_suspend_triggered_at", "autoSuspendTriggeredAt", default=None),
                int(g(item, "reminder_stage", "reminderStage", default=0) or 0),
                g(item, "last_reminder_sent_at", "lastReminderSentAt", default=None),
                str(g(item, "last_reminder_error", "lastReminderError", default="")),
            )
        )
        result.accepted += 1
    if not ctx.dry_run and pending:
        ctx.db.executemany(
            """
            INSERT OR REPLACE INTO invoices (
                id, invoice_number, company_id, recipient_email, invoice_date, invoice_period, description,
                net_amount, vat_rate, vat_amount, total_amount, status, error_message, sent_at,
                rendered_html, created_by_user_id, created_at, due_date, paid_at,
                auto_suspend_triggered_at, reminder_stage, last_reminder_sent_at, last_reminder_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            pending,
        )
    return result


DEPLOY_FIELDS = [
    ("company_id", "companyId"),
    ("worker_id", "workerId"),
    ("work_date", "workDate", "date"),
    ("location_label", "locationLabel", "location"),
]


def apply_deployment_days(ctx: ApplyContext, rows: list[dict[str, Any]]) -> DomainResult:
    result = DomainResult(domain="deployment_days")
    pending: list[tuple] = []
    for item in rows:
        did = str(g(item, "id", default="")).strip()
        wid = str(g(item, "worker_id", "workerId", default="")).strip()
        cid = str(g(item, "company_id", "companyId", default=ctx.company_id) or ctx.company_id).strip()
        work_date = str(g(item, "work_date", "workDate", "date", default="")).strip()
        if not did or not wid or not work_date:
            result.skipped_invalid += 1
            continue
        existing = fetch_by_id(ctx.db, "worker_deployment_days", did)
        same = bool(existing) and fingerprint_match(existing, {**item, "company_id": cid, "worker_id": wid}, DEPLOY_FIELDS)
        action = decide_row_action(exists=bool(existing), same=same, merge_mode=ctx.merge_mode)
        if action == "unchanged":
            result.unchanged += 1
            continue
        if action == "skip":
            result.conflicts += 1
            result.conflict_ids.append(did)
            continue
        if action == "fail":
            result.conflicts += 1
            result.conflict_ids.append(did)
            result.error = f"conflict:deployment_days:{did}"
            return result
        pending.append(
            (
                did,
                cid,
                wid,
                work_date,
                str(g(item, "location_label", "locationLabel", "location", default="")),
                str(g(item, "shift_start", "shiftStart", default="")),
                str(g(item, "shift_end", "shiftEnd", default="")),
                str(g(item, "notes", default="")),
                str(g(item, "source", default="import") or "import"),
                str(g(item, "updated_at", "updatedAt", default=utc_now_iso())),
            )
        )
        result.accepted += 1
    if not ctx.dry_run and pending:
        try:
            ctx.db.executemany(
                """
                INSERT OR REPLACE INTO worker_deployment_days (
                    id, company_id, worker_id, work_date, location_label, shift_start, shift_end, notes, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                pending,
            )
        except Exception as exc:
            result.error = str(exc)
            result.accepted = 0
    return result


def apply_leave_requests(ctx: ApplyContext, rows: list[dict[str, Any]]) -> DomainResult:
    result = DomainResult(domain="leave_requests")
    for item in rows:
        lid = str(g(item, "id", default="")).strip()
        wid = str(g(item, "worker_id", "workerId", default="")).strip()
        cid = str(g(item, "company_id", "companyId", default=ctx.company_id) or ctx.company_id).strip()
        if not lid or not wid:
            result.skipped_invalid += 1
            continue
        existing = fetch_by_id(ctx.db, "leave_requests", lid)
        same = bool(existing) and values_equal(existing.get("status"), g(item, "status", default=None)) and values_equal(
            existing.get("start_date"), g(item, "start_date", "startDate", default=None)
        )
        action = decide_row_action(exists=bool(existing), same=same, merge_mode=ctx.merge_mode)
        if action == "unchanged":
            result.unchanged += 1
            continue
        if action == "skip":
            result.conflicts += 1
            result.conflict_ids.append(lid)
            continue
        if action == "fail":
            result.conflicts += 1
            result.conflict_ids.append(lid)
            result.error = f"conflict:leave_requests:{lid}"
            return result
        if ctx.dry_run:
            result.accepted += 1
            continue
        try:
            cols = [c[1] for c in ctx.db.execute("PRAGMA table_info(leave_requests)").fetchall()]
        except Exception:
            result.error = "leave_requests_unavailable"
            return result
        payload = {
            "id": lid,
            "company_id": cid,
            "worker_id": wid,
            "status": str(g(item, "status", default="ausstehend") or "ausstehend"),
            "start_date": str(g(item, "start_date", "startDate", default="")),
            "end_date": str(g(item, "end_date", "endDate", default="")),
            "type": str(g(item, "type", "leave_type", "leaveType", default="urlaub") or "urlaub"),
            "note": str(g(item, "note", "notes", default="")),
            "days_count": int(g(item, "days_count", "daysCount", default=0) or 0),
            "created_at": str(g(item, "created_at", "createdAt", default=utc_now_iso())),
        }
        use_cols = [c for c in payload.keys() if c in cols]
        if "id" not in use_cols:
            result.skipped_invalid += 1
            continue
        ctx.db.execute(
            f"INSERT OR REPLACE INTO leave_requests ({', '.join(use_cols)}) VALUES ({', '.join('?' for _ in use_cols)})",
            tuple(payload[c] for c in use_cols),
        )
        result.accepted += 1
    return result
