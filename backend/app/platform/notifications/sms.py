"""Optional SMS delivery (Twilio REST API via env vars)."""
from __future__ import annotations

import base64
import os
import urllib.error
import urllib.parse
import urllib.request


def sms_configured() -> bool:
    return bool(
        os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        and os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        and os.getenv("TWILIO_FROM_NUMBER", "").strip()
    )


def send_sms(*, to: str, body: str) -> tuple[bool, str]:
    to = str(to or "").strip()
    body = str(body or "").strip()
    if not to or not body:
        return False, "missing_to_or_body"
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
