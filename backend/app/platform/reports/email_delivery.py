"""Email delivery for PDF reports."""
from __future__ import annotations

import base64
import os
import smtplib
from email.message import EmailMessage
from typing import Any, Tuple

from backend.app.core.platform_env import default_noreply_email, mirror_platform_env

mirror_platform_env()


def _html_body(plain: str) -> str:
    html = (plain or "").strip().replace("\n", "<br>\n")
    return f"<html><body style='font-family:sans-serif;line-height:1.5'>{html}</body></html>"


def _smtp_config() -> Tuple[str, int, str, str, bool, str, str]:
    host = (os.getenv("SMTP_HOST") or "").strip()
    port = int(os.getenv("SMTP_PORT") or 587)
    user = (os.getenv("SMTP_USERNAME") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or "").strip()
    use_tls = str(os.getenv("SMTP_USE_TLS", "1")).strip().lower() in {"1", "true", "yes"}
    sender = (os.getenv("SMTP_SENDER_EMAIL") or user or default_noreply_email()).strip()
    sender_name = (os.getenv("SMTP_SENDER_NAME") or "WorkPass").strip()
    if host:
        return host, port, user, password, use_tls, sender, sender_name
    from backend.server import get_db

    row = get_db().execute(
        """
        SELECT smtp_host, smtp_port, smtp_username, smtp_password, smtp_use_tls,
               smtp_sender_email, smtp_sender_name
        FROM settings WHERE id = 1
        """
    ).fetchone()
    if not row or not str(row["smtp_host"] or "").strip():
        if row:
            sender = str(row["smtp_sender_email"] or row["smtp_username"] or sender).strip()
            sender_name = str(row["smtp_sender_name"] or sender_name).strip()
        return "", port, user, password, use_tls, sender, sender_name
    return (
        str(row["smtp_host"] or "").strip(),
        int(row["smtp_port"] or 587),
        str(row["smtp_username"] or "").strip(),
        str(row["smtp_password"] or ""),
        int(row["smtp_use_tls"] or 0) == 1,
        str(row["smtp_sender_email"] or row["smtp_username"] or default_noreply_email()).strip(),
        str(row["smtp_sender_name"] or "WorkPass").strip(),
    )


def _api_attachments(
    *,
    pdf_bytes: bytes | None = None,
    pdf_filename: str = "baupass-report.pdf",
    attachments: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    api_atts: list[dict[str, str]] = []
    if pdf_bytes:
        api_atts.append(
            {
                "filename": pdf_filename[:120],
                "content_b64": base64.b64encode(pdf_bytes).decode("ascii"),
                "mime_type": "application/pdf",
            }
        )
    for att in attachments or []:
        data = att.get("data")
        if not data:
            continue
        maintype = str(att.get("maintype") or "application")
        subtype = str(att.get("subtype") or "octet-stream")
        api_atts.append(
            {
                "filename": str(att.get("filename") or "attachment.bin")[:120],
                "content_b64": base64.b64encode(data).decode("ascii"),
                "mime_type": f"{maintype}/{subtype}",
            }
        )
    return api_atts


def _send_via_smtp(
    *,
    to: str,
    subject: str,
    body_text: str,
    host: str,
    port: int,
    user: str,
    password: str,
    use_tls: bool,
    sender: str,
    sender_name: str,
    pdf_bytes: bytes | None = None,
    pdf_filename: str = "baupass-report.pdf",
    attachments: list[dict[str, Any]] | None = None,
) -> Tuple[bool, str]:
    msg = EmailMessage()
    msg["Subject"] = subject[:200]
    msg["From"] = f"{sender_name} <{sender}>"
    msg["To"] = to.strip()
    plain = (body_text or "").strip()
    msg.set_content(plain)
    msg.add_alternative(_html_body(plain), subtype="html")
    if pdf_bytes:
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=pdf_filename[:120],
        )
    for att in attachments or []:
        data = att.get("data")
        if not data:
            continue
        msg.add_attachment(
            data,
            maintype=str(att.get("maintype") or "application"),
            subtype=str(att.get("subtype") or "octet-stream"),
            filename=str(att.get("filename") or "attachment.bin")[:120],
        )

    try:
        timeout = max(5, int(os.getenv("BAUPASS_SMTP_TIMEOUT_SECONDS", "12")))
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=timeout) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                if use_tls:
                    smtp.starttls()
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
        return True, ""
    except Exception as exc:
        return False, str(exc)[:300]


def _send_report_email(
    *,
    to: str,
    subject: str,
    body_text: str,
    pdf_bytes: bytes | None = None,
    pdf_filename: str = "baupass-report.pdf",
    attachments: list[dict[str, Any]] | None = None,
) -> Tuple[bool, str]:
    api_atts = _api_attachments(
        pdf_bytes=pdf_bytes,
        pdf_filename=pdf_filename,
        attachments=attachments,
    )
    if not api_atts:
        return False, "Keine Anhänge."

    host, port, user, password, use_tls, sender, sender_name = _smtp_config()
    plain = (body_text or "").strip()
    html = _html_body(plain)

    from backend.server import _send_via_any_api

    ok, err, _provider = _send_via_any_api(
        subject[:200],
        sender,
        sender_name,
        to.strip(),
        plain,
        html,
        attachments=api_atts,
    )
    if ok:
        return True, ""

    if host:
        ok_smtp, smtp_err = _send_via_smtp(
            to=to,
            subject=subject,
            body_text=body_text,
            host=host,
            port=port,
            user=user,
            password=password,
            use_tls=use_tls,
            sender=sender,
            sender_name=sender_name,
            pdf_bytes=pdf_bytes,
            pdf_filename=pdf_filename,
            attachments=attachments,
        )
        if ok_smtp:
            return True, ""
        err = f"{err}; SMTP: {smtp_err}" if err else smtp_err

    if not host and err:
        return False, err
    return False, err or "SMTP nicht konfiguriert (Einstellungen oder Railway Variables)."


def send_attachments_email(
    *,
    to: str,
    subject: str,
    body_text: str,
    attachments: list[dict[str, Any]],
) -> Tuple[bool, str]:
    """Send email with one or more attachments (no PDF required)."""
    return _send_report_email(
        to=to,
        subject=subject,
        body_text=body_text,
        attachments=attachments,
    )


def send_pdf_report_email(
    *,
    to: str,
    subject: str,
    body_text: str,
    pdf_bytes: bytes,
    filename: str = "baupass-report.pdf",
    extra_attachments: list[dict[str, Any]] | None = None,
) -> Tuple[bool, str]:
    return _send_report_email(
        to=to,
        subject=subject,
        body_text=body_text,
        pdf_bytes=pdf_bytes,
        pdf_filename=filename,
        attachments=extra_attachments,
    )
