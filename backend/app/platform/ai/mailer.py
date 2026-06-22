"""Send AI briefing emails via platform SMTP env or settings row."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from typing import Tuple


def send_ai_briefing_email(*, to: str, subject: str, body_text: str) -> Tuple[bool, str]:
    host = (os.getenv("SMTP_HOST") or "").strip()
    port = int(os.getenv("SMTP_PORT") or 587)
    user = (os.getenv("SMTP_USERNAME") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or "").strip()
    use_tls = str(os.getenv("SMTP_USE_TLS", "1")).strip().lower() in {"1", "true", "yes"}
    sender = (os.getenv("SMTP_SENDER_EMAIL") or user or "noreply@baupass.de").strip()
    sender_name = (os.getenv("SMTP_SENDER_NAME") or "SUPPIX AI").strip()

    if not host:
        return False, "SMTP_HOST nicht konfiguriert (Railway Variables)."

    msg = EmailMessage()
    msg["Subject"] = subject[:200]
    msg["From"] = f"{sender_name} <{sender}>"
    msg["To"] = to
    plain = body_text.strip()
    msg.set_content(plain)
    html = plain.replace("\n", "<br>\n")
    msg.add_alternative(f"<html><body style='font-family:sans-serif'>{html}</body></html>", subtype="html")

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
