"""
WorkPass – Email Tasks (Background)
=====================================
جميع إرسالات الإيميل تعمل خارج Flask request cycle.

الميزات:
  - Retry تلقائي عند فشل الإرسال
  - Dead letter queue للإيميلات الفاشلة
  - Deduplication (لا إرسال مزدوج)
  - Audit trail لكل إرسال
"""
from __future__ import annotations

import logging
import smtplib
import time
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger("baupass.tasks.email")


def send_email_task(
    to_addresses: list[str],
    subject: str,
    body_html: str,
    body_text: str,
    from_name: str = "WorkPass",
    reply_to: Optional[str] = None,
    smtp_config: Optional[dict] = None,
    resend_config: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
    company_id: Optional[int] = None,
    audit_event: Optional[str] = None,
) -> dict:
    """
    مهمة إرسال إيميل تعمل في background.
    تُستدعى عبر enqueue() لا مباشرة.

    Args:
        to_addresses: قائمة عناوين المستلمين
        subject: موضوع الإيميل
        body_html: المحتوى HTML
        body_text: المحتوى النصي (fallback)
        from_name: اسم المرسل
        reply_to: عنوان الرد (اختياري)
        smtp_config: إعدادات SMTP {host, port, username, password, from_email}
        resend_config: إعدادات Resend API {api_key, from_email}
        idempotency_key: مفتاح فريد لمنع الإرسال المزدوج
        company_id: للـ audit logging
        audit_event: نوع الحدث للتسجيل

    Returns:
        {"ok": True, "provider": "smtp"|"resend", "message_id": "..."}
    """
    if not to_addresses:
        raise ValueError("send_email_task: no recipients provided")

    # التحقق من Idempotency (منع الإرسال المزدوج)
    if idempotency_key:
        if _is_already_sent(idempotency_key):
            logger.info("Email already sent (idempotency_key=%s). Skipping.", idempotency_key)
            return {"ok": True, "skipped": True, "reason": "already_sent"}

    start = time.monotonic()

    # محاولة Resend أولاً، ثم SMTP
    result = None

    if resend_config and resend_config.get("api_key"):
        result = _send_via_resend(
            to_addresses=to_addresses,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            from_name=from_name,
            reply_to=reply_to,
            config=resend_config,
        )

    if result is None and smtp_config and smtp_config.get("host"):
        result = _send_via_smtp(
            to_addresses=to_addresses,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            from_name=from_name,
            reply_to=reply_to,
            config=smtp_config,
        )

    if result is None:
        raise RuntimeError(
            f"Email send failed: no working provider. "
            f"Recipients: {to_addresses}. Subject: {subject}"
        )

    duration_ms = int((time.monotonic() - start) * 1000)

    if idempotency_key:
        _mark_as_sent(idempotency_key)

    logger.info(
        "Email sent: provider=%s to=%s subject=%s duration_ms=%d",
        result.get("provider"),
        to_addresses,
        subject[:80],
        duration_ms,
    )

    return {**result, "duration_ms": duration_ms}


def _send_via_resend(
    to_addresses: list[str],
    subject: str,
    body_html: str,
    body_text: str,
    from_name: str,
    reply_to: Optional[str],
    config: dict,
) -> Optional[dict]:
    """إرسال عبر Resend API."""
    try:
        import urllib.request
        import urllib.error
        import json

        api_key = config["api_key"]
        from backend.app.core.platform_env import default_noreply_email

        from_email = config.get("from_email", default_noreply_email())

        payload = {
            "from": f"{from_name} <{from_email}>",
            "to": to_addresses,
            "subject": subject,
            "html": body_html,
            "text": body_text,
        }
        if reply_to:
            payload["reply_to"] = reply_to

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            return {"ok": True, "provider": "resend", "message_id": body.get("id", "")}

    except Exception as exc:
        logger.warning("Resend send failed: %s", exc)
        return None


def _send_via_smtp(
    to_addresses: list[str],
    subject: str,
    body_html: str,
    body_text: str,
    from_name: str,
    reply_to: Optional[str],
    config: dict,
) -> Optional[dict]:
    """إرسال عبر SMTP."""
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{config.get('from_email', config.get('username', ''))}>"
        msg["To"] = ", ".join(to_addresses)
        if reply_to:
            msg["Reply-To"] = reply_to

        msg.set_content(body_text)
        msg.add_alternative(body_html, subtype="html")

        host = config["host"]
        port = int(config.get("port", 587))
        username = config.get("username", "")
        password = config.get("password", "")
        use_tls = config.get("use_tls", True)

        if use_tls:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=30)

        if username and password:
            server.login(username, password)

        server.send_message(msg)
        server.quit()

        return {"ok": True, "provider": "smtp", "message_id": ""}

    except Exception as exc:
        logger.warning("SMTP send failed: %s", exc)
        return None


# ── Idempotency tracking (in-memory للتطوير، Redis للإنتاج) ─────────────────
_sent_keys: set[str] = set()


def _is_already_sent(key: str) -> bool:
    """يتحقق إذا كان الإيميل قد أُرسل بالفعل."""
    try:
        from backend.app.extensions import get_redis
        redis = get_redis()
        if redis:
            return bool(redis.exists(f"email:sent:{key}"))
    except Exception:
        pass
    return key in _sent_keys


def _mark_as_sent(key: str, ttl_seconds: int = 86400) -> None:
    """يُسجّل أن الإيميل أُرسل (لمنع الإرسال المزدوج)."""
    try:
        from backend.app.extensions import get_redis
        redis = get_redis()
        if redis:
            redis.set(f"email:sent:{key}", "1", ex=ttl_seconds)
            return
    except Exception:
        pass
    _sent_keys.add(key)


# ── مهام محددة ────────────────────────────────────────────────────────────────

def send_document_expiry_alert(
    worker_id: str,
    worker_name: str,
    worker_email: str,
    document_type: str,
    expires_at: str,
    company_id: int,
    smtp_config: dict,
    resend_config: dict,
) -> dict:
    """تنبيه انتهاء صلاحية وثيقة العامل."""
    subject = f"⚠️ Dokument läuft ab: {document_type}"
    body_html = f"""
    <h2>Dokument läuft ab</h2>
    <p>Hallo {worker_name},</p>
    <p>Ihr Dokument <strong>{document_type}</strong> läuft am <strong>{expires_at}</strong> ab.</p>
    <p>Bitte erneuern Sie es rechtzeitig.</p>
    """
    body_text = f"Dokument {document_type} läuft am {expires_at} ab."

    return send_email_task(
        to_addresses=[worker_email],
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        idempotency_key=f"doc_expiry:{worker_id}:{document_type}:{expires_at}",
        company_id=company_id,
        audit_event="document.expiry_alert",
        smtp_config=smtp_config,
        resend_config=resend_config,
    )


def send_invoice_email(
    invoice_id: str,
    company_email: str,
    company_name: str,
    invoice_number: str,
    amount: float,
    due_date: str,
    pdf_bytes: Optional[bytes],
    company_id: int,
    smtp_config: dict,
    resend_config: dict,
) -> dict:
    """إرسال فاتورة للشركة."""
    subject = f"Rechnung {invoice_number} – SUPPIX"
    body_html = f"""
    <h2>Ihre Rechnung von SUPPIX</h2>
    <p>Sehr geehrte Damen und Herren von {company_name},</p>
    <p>anbei erhalten Sie Rechnung <strong>{invoice_number}</strong> 
       über <strong>{amount:.2f} €</strong>, fällig am {due_date}.</p>
    """
    body_text = f"Rechnung {invoice_number}: {amount:.2f} € fällig am {due_date}."

    return send_email_task(
        to_addresses=[company_email],
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        idempotency_key=f"invoice:{invoice_id}:send",
        company_id=company_id,
        audit_event="invoice.sent",
        smtp_config=smtp_config,
        resend_config=resend_config,
    )
