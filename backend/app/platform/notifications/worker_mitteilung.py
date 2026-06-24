"""Unified worker Mitteilungen: in-app inbox + Web Push / FCM + e-mail."""
from __future__ import annotations

import html
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


def _worker_app_link(action_url: str) -> str:
    from backend.server import get_public_base_url

    base = get_public_base_url().rstrip("/")
    path_map = {
        "documents": "/emp-app.html#documents",
        "deployment-plan": "/emp-app.html#einsatzplan",
        "deployment_plan": "/emp-app.html#einsatzplan",
        "leave": "/emp-app.html#leave",
    }
    key = str(action_url or "").strip().lower()
    return f"{base}{path_map.get(key, '/emp-app.html')}"


def _send_worker_mitteilung_email(
    db,
    worker_id: str,
    *,
    title: str,
    message: str,
    action_url: str = "",
) -> bool:
    try:
        from backend.server import _send_email_to_worker

        app_link = _worker_app_link(action_url)
        title_safe = html.escape(str(title or "Mitteilung"))
        message_safe = html.escape(str(message or ""))
        text_body = f"{message}\n\nIn der Mitarbeiter-App öffnen:\n{app_link}\n"
        html_body = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f4f6f8;margin:0;padding:24px;">
<table width="100%"><tr><td align="center">
<table width="560" style="background:#fff;border-radius:10px;padding:24px;max-width:560px;">
  <tr><td>
    <h2 style="margin:0 0 12px;color:#1f6feb;">{title_safe}</h2>
    <p style="color:#333;line-height:1.5;">{message_safe}</p>
    <p style="margin-top:20px;">
      <a href="{app_link}" style="display:inline-block;background:#1f6feb;color:#fff;
        text-decoration:none;padding:10px 18px;border-radius:8px;font-weight:600;">
        In der Mitarbeiter-App öffnen
      </a>
    </p>
  </td></tr>
</table></td></tr></table></body></html>"""
        return bool(
            _send_email_to_worker(
                db,
                str(worker_id),
                f"SUPPIX: {title}"[:180],
                text_body,
                html_body,
            )
        )
    except Exception:
        return False


def notify_worker_mitteilung(
    db,
    worker_id: str,
    *,
    notif_type: str,
    title: str,
    message: str,
    action_url: str = "",
    push_tag: str | None = None,
    send_email: bool = True,
) -> dict[str, Any]:
    """
    Store a Mitteilung in ``notifications``, optional e-mail, and push if subscribed.
    Caller is responsible for ``db.commit()``.
    """
    notif_id = None
    push_sent = 0
    email_sent = False
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
                str(title or "SUPPIX")[:120],
                str(message or "")[:240],
                tag=tag,
            )
            or 0
        )
        if send_email:
            email_sent = _send_worker_mitteilung_email(
                db,
                str(worker_id),
                title=str(title or "Mitteilung"),
                message=str(message or ""),
                action_url=str(action_url or ""),
            )
    except Exception:
        pass
    return {
        "ok": True,
        "notificationId": notif_id,
        "pushSent": push_sent,
        "emailSent": email_sent,
    }


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
