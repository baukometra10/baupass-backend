"""Unified worker Mitteilungen: in-app inbox + Web Push / FCM."""
from __future__ import annotations

from typing import Any

_DOC_LABELS_DE: dict[str, str] = {
    "lohnabrechnung": "Lohnabrechnung",
    "einsatzplan": "Einsatzplan",
    "personalausweis": "Personalausweis",
    "mindestlohnnachweis": "Mindestlohnnachweis",
    "aufenthaltstitel": "Aufenthaltstitel",
    "arbeitserlaubnis": "Arbeitserlaubnis",
    "fuehrerschein": "Führerschein",
    "sicherheitsunterweisung": "Sicherheitsunterweisung",
    "sonstiges": "Dokument",
}


def document_type_label(doc_type: str) -> str:
    key = str(doc_type or "").strip().lower()
    if key in _DOC_LABELS_DE:
        return _DOC_LABELS_DE[key]
    return key.replace("_", " ").replace("-", " ").strip().title() or "Dokument"


def notify_worker_mitteilung(
    db,
    worker_id: str,
    *,
    notif_type: str,
    title: str,
    message: str,
    action_url: str = "",
    push_tag: str | None = None,
) -> dict[str, Any]:
    """
    Store a Mitteilung in ``notifications`` and send push if the worker subscribed.
    Caller is responsible for ``db.commit()``.
    """
    notif_id = None
    try:
        from backend.server import _create_worker_notification, _send_push_to_worker

        notif_id = _create_worker_notification(
            db,
            str(worker_id),
            str(notif_type or "general")[:64],
            str(title or "Mitteilung")[:200],
            str(message or "")[:1000],
            action_url=str(action_url or "")[:500],
        )
        tag = str(push_tag or notif_type or "notification").replace("_", "-")
        push_sent = int(
            _send_push_to_worker(
                db,
                str(worker_id),
                str(title or "BauPass")[:120],
                str(message or "")[:240],
                tag=tag,
            )
            or 0
        )
    except Exception:
        push_sent = 0
    return {"ok": True, "notificationId": notif_id, "pushSent": push_sent}


def notify_worker_new_document(
    db,
    worker_id: str,
    *,
    doc_type: str,
    filename: str = "",
) -> dict[str, Any]:
    """Mitteilung when admin assigns or uploads a worker document."""
    from backend.server import is_payroll_doc_type

    label = document_type_label(doc_type)
    name = str(filename or "").strip() or label
    if is_payroll_doc_type(doc_type):
        notif_type = "payroll_document"
        title = "Neue Lohnabrechnung"
        action_url = "documents"
        push_tag = "payroll-document"
    elif str(doc_type or "").strip().lower() == "einsatzplan":
        notif_type = "deployment_plan"
        title = "Einsatzplan"
        action_url = "deployment-plan"
        push_tag = "deployment-plan"
    else:
        notif_type = "worker_document"
        title = f"Neues Dokument: {label}"
        action_url = "documents"
        push_tag = "worker-document"
    message = f"{name} ist in der Mitarbeiter-App unter Dokumente verfügbar."
    return notify_worker_mitteilung(
        db,
        worker_id,
        notif_type=notif_type,
        title=title,
        message=message,
        action_url=action_url,
        push_tag=push_tag,
    )


def notify_worker_deployment_plan(
    db,
    worker_id: str,
    *,
    year: int,
    month: int,
) -> dict[str, Any]:
    month_label = f"{int(month):02d}/{int(year)}"
    return notify_worker_mitteilung(
        db,
        worker_id,
        notif_type="deployment_plan",
        title="Einsatzplan",
        message=f"Ihr Einsatzplan für {month_label} ist in der App verfügbar.",
        action_url="deployment-plan",
        push_tag="deployment-plan",
    )
