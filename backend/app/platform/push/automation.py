"""Automatic FCM push hooks for hybrid worker app events."""
from __future__ import annotations

from typing import Any


def _notify_inbox(company_id: str | int | None, *, source: str) -> None:
    try:
        from backend.app.platform.inbox.events import notify_inbox_changed

        notify_inbox_changed(company_id, source=source)
    except Exception:
        pass


def push_to_worker(
    db,
    worker_id: str,
    title: str,
    body: str,
    *,
    tag: str = "notification",
    company_id: str | int | None = None,
    notify_admin_inbox: bool = False,
    inbox_source: str = "push",
) -> dict[str, Any]:
    """Deliver native FCM push; optionally refresh admin inbox badge."""
    from .delivery import deliver_worker_push

    delivery = deliver_worker_push(
        db,
        str(worker_id),
        title,
        body,
        tag=tag,
        company_id=str(company_id) if company_id is not None else None,
    )
    if notify_admin_inbox and company_id:
        _notify_inbox(company_id, source=inbox_source)
    return delivery


def push_leave_submitted(
    db,
    *,
    worker_id: str,
    company_id: str | int,
    req_type_label: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Confirm submission to worker; refresh admin inbox."""
    title = "Antrag eingereicht"
    body = f"{req_type_label} {start_date}–{end_date} — wird geprüft."
    delivery: dict[str, Any] = {"pushSent": 0}
    try:
        from backend.app.platform.notifications.worker_mitteilung import notify_worker_mitteilung

        delivery = notify_worker_mitteilung(
            db,
            worker_id,
            notif_type="leave_request",
            title=title,
            message=body,
            action_url="leave",
            push_tag="leave-request-status",
        )
    except Exception:
        pass
    if company_id:
        _notify_inbox(company_id, source="leave_submitted")
    return delivery


def push_leave_decision(
    db,
    row,
    new_status: str,
    *,
    review_note: str = "",
) -> dict[str, Any]:
    """Notify worker when leave is approved or rejected."""
    type_labels = {"urlaub": "Urlaub", "krank": "Krankmeldung", "sonstiges": "Antrag"}
    req_type_label = type_labels.get(row["type"], row["type"])
    if new_status == "genehmigt":
        tag = "leave-approved"
        label = "genehmigt ✓"
    elif new_status == "abgelehnt":
        tag = "leave-denied"
        label = "abgelehnt ✗"
    else:
        tag = "leave-request-status"
        label = new_status
    body = f"{req_type_label} {row['start_date']}–{row['end_date']}"
    if review_note:
        body += f" — {review_note[:80]}"
    title = f"Antrag {label}"
    delivery: dict[str, Any] = {"pushSent": 0}
    try:
        from backend.app.platform.notifications.worker_mitteilung import notify_worker_mitteilung

        delivery = notify_worker_mitteilung(
            db,
            row["worker_id"],
            notif_type="leave_request",
            title=title,
            message=body,
            action_url="leave",
            push_tag=tag,
        )
    except Exception:
        pass
    if row["company_id"]:
        _notify_inbox(row["company_id"], source="leave_decision")
    return delivery


def push_security_alert(
    db,
    *,
    worker_id: str,
    company_id: str | int,
    title: str,
    severity: str,
) -> dict[str, Any]:
    """Push worker on high/critical security findings (hybrid app)."""
    sev = (severity or "medium").lower()
    if sev not in ("critical", "high"):
        return {"delivered": False, "pushSent": 0, "skipped": "severity_below_threshold"}
    delivery = push_to_worker(
        db,
        worker_id,
        "SUPPIX Sicherheit",
        (title or "Sicherheitshinweis")[:200],
        tag="ops-notify",
        company_id=company_id,
        notify_admin_inbox=True,
        inbox_source="security_alert",
    )
    try:
        from backend.app.platform.inbox.events import notify_inbox_changed

        notify_inbox_changed(
            company_id,
            source="security_alert",
            alert_title=title or "Security alert",
            alert_message=title or "",
            severity=sev,
        )
    except Exception:
        pass
    return delivery


def push_document_expiry(
    db,
    *,
    worker_id: str,
    company_id: str | int,
    doc_type: str,
    expiry_date: str,
) -> dict[str, Any]:
    return push_to_worker(
        db,
        worker_id,
        "Dokument läuft ab",
        f"{doc_type} bis {expiry_date}",
        tag="document-expiry",
        company_id=company_id,
    )
