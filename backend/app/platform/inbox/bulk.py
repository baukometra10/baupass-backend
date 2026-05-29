"""Bulk inbox actions for admin operations."""
from __future__ import annotations

from typing import Any


def run_bulk_inbox_action(
    db,
    *,
    company_id: str,
    user_id: str,
    action: str,
    item_ids: list[str] | None = None,
    decision: str = "approve",
) -> dict[str, Any]:
    from .service import build_operations_inbox

    cid = str(company_id or "").strip()
    if not cid:
        return {"ok": False, "error": "company_required"}

    dash = build_operations_inbox(db, cid, role="company-admin", limit=200)
    items = dash.get("items") or []
    wanted = {str(i).strip() for i in (item_ids or []) if str(i).strip()}
    if wanted:
        items = [it for it in items if it.get("id") in wanted]

    if action == "push_document_reminders":
        return _bulk_push_documents(db, cid, items)

    if action == "approve_pending_leave":
        return _bulk_leave_decision(db, cid, user_id, items, decision=decision)

    if action == "ack_system_alerts":
        return _bulk_ack_system(db, cid, items)

    return {"ok": False, "error": "unknown_action"}


def _bulk_push_documents(db, company_id: str, items: list[dict]) -> dict[str, Any]:
    from backend.app.platform.push.automation import push_document_expiry

    doc_items = [it for it in items if str(it.get("id", "")).startswith("doc:")]
    sent = 0
    failed = 0
    for it in doc_items:
        doc_id = str(it["id"])[4:]
        row = db.execute(
            """
            SELECT wd.doc_type, wd.expiry_date, wd.worker_id, w.company_id
            FROM worker_documents wd
            JOIN workers w ON w.id = wd.worker_id
            WHERE wd.id = ? AND w.company_id = ?
            """,
            (doc_id, company_id),
        ).fetchone()
        if not row:
            failed += 1
            continue
        delivery = push_document_expiry(
            db,
            worker_id=str(row["worker_id"]),
            company_id=company_id,
            doc_type=str(row["doc_type"] or "Dokument"),
            expiry_date=str(row["expiry_date"] or ""),
        )
        if int(delivery.get("pushSent") or 0) > 0:
            sent += 1
        else:
            failed += 1
    try:
        from .events import notify_inbox_changed

        notify_inbox_changed(company_id, source="bulk_doc_push")
    except Exception:
        pass
    return {
        "ok": True,
        "action": "push_document_reminders",
        "processed": len(doc_items),
        "pushSent": sent,
        "failed": failed,
    }


def _bulk_leave_decision(
    db, company_id: str, user_id: str, items: list[dict], *, decision: str
) -> dict[str, Any]:
    from backend.app.platform.ai.actions import execute_action

    leave_items = [it for it in items if str(it.get("id", "")).startswith("leave:")]
    ok_count = 0
    push_total = 0
    errors: list[str] = []
    act = "approve_leave_request" if decision == "approve" else "reject_leave_request"
    for it in leave_items:
        leave_id = str(it["id"])[6:]
        result = execute_action(
            db,
            company_id=company_id,
            user_id=user_id,
            action=act,
            params={"leave_id": leave_id},
        )
        if result.get("ok"):
            ok_count += 1
            push_total += int(result.get("pushSent") or 0)
        else:
            errors.append(f"{leave_id}:{result.get('error', 'failed')}")
    try:
        from .events import notify_inbox_changed

        notify_inbox_changed(company_id, source="bulk_leave")
    except Exception:
        pass
    return {
        "ok": ok_count > 0 or not errors,
        "action": act,
        "processed": len(leave_items),
        "approvedOrRejected": ok_count,
        "pushSent": push_total,
        "errors": errors[:10],
    }


def _bulk_ack_system(db, company_id: str, items: list[dict]) -> dict[str, Any]:
    from .service import resolve_inbox_item

    sys_items = [it for it in items if str(it.get("id", "")).startswith("sys:")]
    ok_count = 0
    for it in sys_items:
        r = resolve_inbox_item(
            db,
            item_id=str(it["id"]),
            company_id=company_id,
            user_id="bulk",
            decision=None,
        )
        if r.get("ok"):
            ok_count += 1
    return {
        "ok": True,
        "action": "ack_system_alerts",
        "processed": len(sys_items),
        "acknowledged": ok_count,
    }
