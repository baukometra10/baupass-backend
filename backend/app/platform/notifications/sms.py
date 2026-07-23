"""Optional SMS delivery via Brevo and/or Twilio."""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request


def _twilio_configured() -> bool:
    return bool(
        os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        and os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        and os.getenv("TWILIO_FROM_NUMBER", "").strip()
    )


def _brevo_api_key() -> str:
    key = (os.getenv("BREVO_API_KEY") or os.getenv("SENDINBLUE_API_KEY") or "").strip()
    if key:
        return key
    try:
        from backend.server import _get_brevo_api_key

        return str(_get_brevo_api_key() or "").strip()
    except Exception:
        return ""


def _brevo_sms_sender() -> str:
    raw = (os.getenv("BREVO_SMS_SENDER") or os.getenv("BREVO_SMS_FROM") or "SUPPIX").strip()
    # Brevo: max 11 alphanumeric for named sender.
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw)[:11]
    return cleaned or "SUPPIX"


def brevo_sms_configured() -> bool:
    return bool(_brevo_api_key() and _brevo_sms_sender())


def sms_configured() -> bool:
    return _twilio_configured() or brevo_sms_configured()


def _send_via_brevo(*, to: str, body: str) -> tuple[bool, str]:
    api_key = _brevo_api_key()
    sender = _brevo_sms_sender()
    if not api_key or not sender:
        return False, "brevo_sms_not_configured"
    recipient = re.sub(r"[^\d+]", "", str(to or "").strip())
    if not recipient:
        return False, "missing_to_or_body"
    payload = json.dumps(
        {
            "sender": sender,
            "recipient": recipient,
            "content": str(body or "")[:700],
            "type": "transactional",
            "unicodeEnabled": True,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.brevo.com/v3/transactionalSMS/sms",
        data=payload,
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return 200 <= resp.status < 300, ""
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:180]
        except Exception:
            detail = ""
        return False, f"brevo_sms_http_{exc.code}:{detail}" if detail else f"brevo_sms_http_{exc.code}"
    except Exception as exc:
        return False, str(exc)[:200]


def _send_via_twilio(*, to: str, body: str) -> tuple[bool, str]:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_number = os.getenv("TWILIO_FROM_NUMBER", "").strip()
    if not (account_sid and auth_token and from_number):
        return False, "sms_not_configured"
    payload = urllib.parse.urlencode({"To": to, "From": from_number, "Body": body[:1500]}).encode()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return 200 <= resp.status < 300, ""
    except urllib.error.HTTPError as exc:
        return False, f"twilio_http_{exc.code}"
    except Exception as exc:
        return False, str(exc)[:200]


def send_sms(*, to: str, body: str) -> tuple[bool, str]:
    to = str(to or "").strip()
    body = str(body or "").strip()
    if not to or not body:
        return False, "missing_to_or_body"

    errors: list[str] = []
    # Prefer Brevo when configured (same stack as transactional email).
    if brevo_sms_configured():
        ok, err = _send_via_brevo(to=to, body=body)
        if ok:
            return True, ""
        errors.append(err or "brevo_sms_failed")
    if _twilio_configured():
        ok, err = _send_via_twilio(to=to, body=body)
        if ok:
            return True, ""
        errors.append(err or "twilio_failed")
    if errors:
        return False, "; ".join(errors)
    return False, "sms_not_configured"
