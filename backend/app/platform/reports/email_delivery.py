"""Email delivery for PDF reports."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from typing import Any, Tuple


def _smtp_config() -> Tuple[str, int, str, str, bool, str, str]:
    host = (os.getenv("SMTP_HOST") or "").strip()
    port = int(os.getenv("SMTP_PORT") or 587)
    user = (os.getenv("SMTP_USERNAME") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or "").strip()
    use_tls = str(os.getenv("SMTP_USE_TLS", "1")).strip().lower() in {"1", "true", "yes"}
    sender = (os.getenv("SMTP_SENDER_EMAIL") or user or "noreply@baupass.de").strip()
    sender_name = (os.getenv("SMTP_SENDER_NAME") or "SUPPIX").strip()
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
        return "", port, user, password, use_tls, sender, sender_name
    return (
        str(row["smtp_host"] or "").strip(),
        int(row["smtp_port"] or 587),
        str(row["smtp_username"] or "").strip(),
        str(row["smtp_password"] or ""),
        int(row["smtp_use_tls"] or 0) == 1,
        str(row["smtp_sender_email"] or row["smtp_username"] or "noreply@baupass.de").strip(),
        str(row["smtp_sender_name"] or "SUPPIX").strip(),
    )


def send_attachments_email(
    *,
    to: str,
    subject: str,
    body_text: str,
    attachments: list[dict[str, Any]],
) -> Tuple[bool, str]:
    """Send email with one or more attachments (no PDF required)."""
    if not attachments:
        return False, "Keine Anhänge."
    host, port, user, password, use_tls, sender, sender_name = _smtp_config()
    if not host:
        return False, "SMTP nicht konfiguriert (Einstellungen oder Railway Variables)."

    msg = EmailMessage()
    msg["Subject"] = subject[:200]
    msg["From"] = f"{sender_name} <{sender}>"
    msg["To"] = to.strip()
    plain = (body_text or "").strip()
    msg.set_content(plain)
    html = plain.replace("\n", "<br>\n")
    msg.add_alternative(
        f"<html><body style='font-family:sans-serif;line-height:1.5'>{html}</body></html>",
        subtype="html",
    )
    for att in attachments:
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


def send_pdf_report_email(
    *,
    to: str,
    subject: str,
    body_text: str,
    pdf_bytes: bytes,
    filename: str = "baupass-report.pdf",
    extra_attachments: list[dict[str, Any]] | None = None,
) -> Tuple[bool, str]:
    host, port, user, password, use_tls, sender, sender_name = _smtp_config()
    if not host:
        return False, "SMTP nicht konfiguriert (Einstellungen oder Railway Variables)."

    msg = EmailMessage()
    msg["Subject"] = subject[:200]
    msg["From"] = f"{sender_name} <{sender}>"
    msg["To"] = to.strip()
    plain = (body_text or "").strip()
    msg.set_content(plain)
    html = plain.replace("\n", "<br>\n")
    msg.add_alternative(
        f"<html><body style='font-family:sans-serif;line-height:1.5'>{html}</body></html>",
        subtype="html",
    )
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=filename[:120],
    )
    for att in extra_attachments or []:
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
