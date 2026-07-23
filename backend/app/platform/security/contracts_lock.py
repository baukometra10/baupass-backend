"""Owner step-up unlock (contracts + sensitive exports) via SMS/email OTP.

OTP codes and fail counters persist in SQLite so multi-worker / restarts stay safe.
Session unlock is shared across contracts and sensitive data exports for the same company.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any

from flask import g, jsonify, request

_log = logging.getLogger("baupass.contracts_lock")

_OTP_TTL_MINUTES = 10
_UNLOCK_TTL_MINUTES_DEFAULT = 15
_OTP_MAX_ATTEMPTS = 5
_OTP_LOCKOUT_SECONDS = 300
_STEP_UP_PURPOSE = "owner"

# Process-local fallback only if DB table is missing (legacy/dev).
_fail_counts: dict[str, tuple[int, float]] = {}
_otp_store: dict[str, tuple[str, float]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


def unlock_ttl_minutes() -> int:
    raw = os.getenv("BAUPASS_CONTRACTS_UNLOCK_TTL_MINUTES", str(_UNLOCK_TTL_MINUTES_DEFAULT)).strip()
    try:
        return max(5, min(120, int(raw)))
    except ValueError:
        return _UNLOCK_TTL_MINUTES_DEFAULT


def normalize_phone(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+") and digits.isdigit() and len(digits) >= 10:
        # Assume DE if local; keep digits and let Twilio reject bad numbers.
        digits = "+" + digits
    if not re.fullmatch(r"\+[1-9]\d{7,14}", digits):
        return ""
    return digits


def mask_phone(phone: str) -> str:
    p = str(phone or "")
    if len(p) < 6:
        return "••••"
    return f"{p[:3]}••••{p[-2:]}"


def mask_email(email: str) -> str:
    e = str(email or "").strip()
    if "@" not in e:
        return ""
    local, _, domain = e.partition("@")
    if len(local) <= 2:
        shown = "*" * len(local)
    else:
        shown = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{shown}@{domain}"


def generate_otp_code(*, digits: int = 6) -> str:
    digits = max(4, min(8, int(digits or 6)))
    lo = 10 ** (digits - 1)
    hi = (10**digits) - 1
    return str(secrets.randbelow(hi - lo + 1) + lo)


def _fail_key(company_id: str, user_id: str) -> str:
    return f"{company_id}:{user_id}"


def _otp_pepper() -> str:
    return (
        os.getenv("BAUPASS_SECRET_KEY")
        or os.getenv("BAUPASS_DQR_SECRET")
        or "baupass-step-up"
    ).strip()


def _hash_otp(code: str) -> str:
    raw = f"{_otp_pepper()}:{str(code or '').strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def ensure_step_up_tables(db) -> None:
    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS step_up_otps (
                purpose TEXT NOT NULL,
                company_id TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (purpose, company_id)
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS step_up_fail_counts (
                purpose TEXT NOT NULL,
                company_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                fail_count INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (purpose, company_id, user_id)
            )
            """
        )
        db.commit()
    except Exception as exc:
        _log.warning("ensure_step_up_tables failed: %s", exc)


def _check_rate_limit(db, company_id: str, user_id: str) -> tuple[bool, int]:
    ensure_step_up_tables(db)
    try:
        row = db.execute(
            """
            SELECT fail_count, locked_until FROM step_up_fail_counts
            WHERE purpose = ? AND company_id = ? AND user_id = ?
            """,
            (_STEP_UP_PURPOSE, str(company_id), str(user_id)),
        ).fetchone()
    except Exception:
        row = None
    if row:
        locked_until = str(row["locked_until"] or "").strip()
        if locked_until and locked_until > _now_iso():
            try:
                until_dt = datetime.strptime(locked_until, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                return False, max(1, int((until_dt - _now()).total_seconds()))
            except ValueError:
                return False, _OTP_LOCKOUT_SECONDS
        if locked_until and locked_until <= _now_iso():
            db.execute(
                "DELETE FROM step_up_fail_counts WHERE purpose = ? AND company_id = ? AND user_id = ?",
                (_STEP_UP_PURPOSE, str(company_id), str(user_id)),
            )
            db.commit()
        return True, 0
    # memory fallback
    key = _fail_key(company_id, user_id)
    entry = _fail_counts.get(key)
    if not entry:
        return True, 0
    count, locked_until_ts = entry
    del count
    now = _now().timestamp()
    if locked_until_ts and now < locked_until_ts:
        return False, int(locked_until_ts - now)
    if locked_until_ts and now >= locked_until_ts:
        _fail_counts.pop(key, None)
        return True, 0
    return True, 0


def _register_fail(db, company_id: str, user_id: str) -> int:
    ensure_step_up_tables(db)
    ok_rate, retry_in = _check_rate_limit(db, company_id, user_id)
    if not ok_rate:
        return retry_in
    try:
        row = db.execute(
            """
            SELECT fail_count, locked_until FROM step_up_fail_counts
            WHERE purpose = ? AND company_id = ? AND user_id = ?
            """,
            (_STEP_UP_PURPOSE, str(company_id), str(user_id)),
        ).fetchone()
        count = int((row["fail_count"] if row else 0) or 0) + 1
        locked_until = ""
        if count >= _OTP_MAX_ATTEMPTS:
            locked_until = (_now() + timedelta(seconds=_OTP_LOCKOUT_SECONDS)).strftime("%Y-%m-%dT%H:%M:%SZ")
            retry = _OTP_LOCKOUT_SECONDS
        else:
            retry = 0
        db.execute(
            "DELETE FROM step_up_fail_counts WHERE purpose = ? AND company_id = ? AND user_id = ?",
            (_STEP_UP_PURPOSE, str(company_id), str(user_id)),
        )
        db.execute(
            """
            INSERT INTO step_up_fail_counts (purpose, company_id, user_id, fail_count, locked_until)
            VALUES (?, ?, ?, ?, ?)
            """,
            (_STEP_UP_PURPOSE, str(company_id), str(user_id), count, locked_until),
        )
        db.commit()
        return retry
    except Exception:
        key = _fail_key(company_id, user_id)
        count, locked_until_ts = _fail_counts.get(key, (0, 0.0))
        now = _now().timestamp()
        if locked_until_ts and now < locked_until_ts:
            return int(locked_until_ts - now)
        count += 1
        if count >= _OTP_MAX_ATTEMPTS:
            _fail_counts[key] = (count, now + _OTP_LOCKOUT_SECONDS)
            return _OTP_LOCKOUT_SECONDS
        _fail_counts[key] = (count, 0.0)
        return 0


def _clear_fails(db, company_id: str, user_id: str) -> None:
    ensure_step_up_tables(db)
    try:
        db.execute(
            "DELETE FROM step_up_fail_counts WHERE purpose = ? AND company_id = ? AND user_id = ?",
            (_STEP_UP_PURPOSE, str(company_id), str(user_id)),
        )
        db.commit()
    except Exception:
        pass
    _fail_counts.pop(_fail_key(company_id, user_id), None)


def company_owner_phone(db, company_id: str) -> str:
    try:
        row = db.execute(
            "SELECT contract_owner_phone FROM companies WHERE id = ?",
            (str(company_id),),
        ).fetchone()
    except Exception:
        return ""
    if not row:
        return ""
    try:
        return str(row["contract_owner_phone"] or "").strip()
    except Exception:
        return str(row[0] or "").strip() if row else ""


def company_owner_email(db, company_id: str) -> str:
    try:
        row = db.execute(
            """
            SELECT contract_owner_email, billing_email
            FROM companies WHERE id = ?
            """,
            (str(company_id),),
        ).fetchone()
    except Exception:
        return ""
    if not row:
        return ""
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    for key in ("contract_owner_email", "billing_email"):
        if key in keys:
            val = str(row[key] or "").strip()
            if val and "@" in val:
                return val
    return ""


def contracts_lock_required(db, company_id: str) -> bool:
    """Lock is active only after an owner phone was configured."""
    return bool(company_owner_phone(db, company_id))


def is_contracts_unlocked(db, token: str | None, company_id: str) -> bool:
    if not contracts_lock_required(db, company_id):
        return True
    tok = str(token or "").strip()
    cid = str(company_id or "").strip()
    if not tok or not cid:
        return False
    try:
        row = db.execute(
            """
            SELECT contracts_unlocked_until, contracts_unlocked_company_id
            FROM sessions WHERE token = ?
            """,
            (tok,),
        ).fetchone()
    except Exception:
        return False
    if not row:
        return False
    until = str(row["contracts_unlocked_until"] or "").strip()
    unlocked_cid = str(row["contracts_unlocked_company_id"] or "").strip()
    if not until or unlocked_cid != cid:
        return False
    return until >= _now_iso()


def unlock_contracts_session(db, token: str, company_id: str) -> str:
    until = (_now() + timedelta(minutes=unlock_ttl_minutes())).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        """
        UPDATE sessions
        SET contracts_unlocked_until = ?, contracts_unlocked_company_id = ?
        WHERE token = ?
        """,
        (until, str(company_id), str(token)),
    )
    db.commit()
    return until


def lock_contracts_session(db, token: str) -> None:
    db.execute(
        """
        UPDATE sessions
        SET contracts_unlocked_until = NULL, contracts_unlocked_company_id = NULL
        WHERE token = ?
        """,
        (str(token),),
    )
    db.commit()


def set_company_owner_contact(
    db,
    company_id: str,
    *,
    phone: str,
    email: str = "",
    actor_user_id: str = "",
) -> None:
    phone_n = normalize_phone(phone)
    if not phone_n:
        raise ValueError("invalid_phone")
    email_n = str(email or "").strip().lower()
    if email_n and "@" not in email_n:
        raise ValueError("invalid_email")
    db.execute(
        """
        UPDATE companies
        SET contract_owner_phone = ?,
            contract_owner_email = ?,
            contract_owner_set_by = ?,
            contract_owner_updated_at = ?
        WHERE id = ?
        """,
        (phone_n, email_n, str(actor_user_id or ""), _now_iso(), str(company_id)),
    )
    db.commit()


def persist_otp(db, company_id: str, code: str) -> None:
    ensure_step_up_tables(db)
    expires = (_now() + timedelta(minutes=_OTP_TTL_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
    code_hash = _hash_otp(code)
    cid = str(company_id)
    try:
        db.execute(
            "DELETE FROM step_up_otps WHERE purpose = ? AND company_id = ?",
            (_STEP_UP_PURPOSE, cid),
        )
        db.execute(
            """
            INSERT INTO step_up_otps (purpose, company_id, code_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (_STEP_UP_PURPOSE, cid, code_hash, expires, _now_iso()),
        )
        db.commit()
    except Exception as exc:
        _log.warning("persist_otp DB failed, using memory fallback: %s", exc)
        _otp_store[cid] = (str(code), _now().timestamp() + (_OTP_TTL_MINUTES * 60))


def consume_otp(db, company_id: str, code: str, *, user_id: str) -> bool:
    ensure_step_up_tables(db)
    ok_rate, retry_in = _check_rate_limit(db, company_id, user_id)
    if not ok_rate:
        raise ValueError(f"rate_limited:{retry_in}")
    cid = str(company_id)
    code_hash = _hash_otp(code)
    try:
        row = db.execute(
            """
            SELECT code_hash, expires_at FROM step_up_otps
            WHERE purpose = ? AND company_id = ?
            """,
            (_STEP_UP_PURPOSE, cid),
        ).fetchone()
    except Exception:
        row = None
    if row:
        expires = str(row["expires_at"] or "")
        stored_hash = str(row["code_hash"] or "")
        if not expires or expires < _now_iso():
            db.execute(
                "DELETE FROM step_up_otps WHERE purpose = ? AND company_id = ?",
                (_STEP_UP_PURPOSE, cid),
            )
            db.commit()
            retry = _register_fail(db, company_id, user_id)
            if retry:
                raise ValueError(f"rate_limited:{retry}")
            return False
        if not secrets.compare_digest(stored_hash, code_hash):
            retry = _register_fail(db, company_id, user_id)
            if retry:
                raise ValueError(f"rate_limited:{retry}")
            return False
        db.execute(
            "DELETE FROM step_up_otps WHERE purpose = ? AND company_id = ?",
            (_STEP_UP_PURPOSE, cid),
        )
        db.commit()
        _clear_fails(db, company_id, user_id)
        _otp_store.pop(cid, None)
        return True

    # Memory fallback (legacy)
    entry = _otp_store.get(cid)
    if not entry:
        retry = _register_fail(db, company_id, user_id)
        if retry:
            raise ValueError(f"rate_limited:{retry}")
        return False
    stored, expires_ts = entry
    if _now().timestamp() > expires_ts:
        _otp_store.pop(cid, None)
        retry = _register_fail(db, company_id, user_id)
        if retry:
            raise ValueError(f"rate_limited:{retry}")
        return False
    if not secrets.compare_digest(str(code or "").strip(), str(stored)):
        retry = _register_fail(db, company_id, user_id)
        if retry:
            raise ValueError(f"rate_limited:{retry}")
        return False
    _otp_store.pop(cid, None)
    _clear_fails(db, company_id, user_id)
    return True


def send_otp_channels(
    db,
    *,
    company_id: str,
    phone: str,
    email: str = "",
    code: str,
) -> dict[str, Any]:
    from backend.app.platform.notifications.sms import send_sms, sms_configured

    sms_ok = False
    sms_err = ""
    email_ok = False
    channels: list[str] = []
    body = f"SUPPIX Vertragszugang: Ihr Code lautet {code}. Gueltig {_OTP_TTL_MINUTES} Minuten."

    if phone and sms_configured():
        sms_ok, sms_err = send_sms(to=phone, body=body)
        if sms_ok:
            channels.append("sms")
    elif phone and not sms_configured():
        sms_err = "sms_not_configured"

    target_email = str(email or "").strip() or company_owner_email(db, company_id)
    if target_email:
        try:
            from backend.server import _send_otp_email_to_user

            email_ok = bool(_send_otp_email_to_user(db, {"email": target_email, "username": "contracts-owner"}, code))
            if email_ok:
                channels.append("email")
        except Exception as exc:
            _log.warning("contracts otp email failed: %s", exc)

    if not channels:
        # Dev fallback: keep code in logs when neither channel works.
        _log.warning(
            "contracts OTP for company %s could not be delivered (sms=%s email=%s). code=%s",
            company_id,
            sms_err or sms_ok,
            email_ok,
            code,
        )
    return {
        "channels": channels,
        "smsOk": sms_ok,
        "smsError": sms_err,
        "emailOk": email_ok,
        "smsConfigured": sms_configured(),
    }


def lock_status(db, *, company_id: str, token: str | None) -> dict[str, Any]:
    from backend.app.platform.notifications.sms import sms_configured

    phone = company_owner_phone(db, company_id)
    email = company_owner_email(db, company_id)
    required = bool(phone)
    unlocked = is_contracts_unlocked(db, token, company_id)
    until = ""
    if unlocked and token:
        try:
            row = db.execute(
                "SELECT contracts_unlocked_until FROM sessions WHERE token = ?",
                (str(token),),
            ).fetchone()
            until = str((row["contracts_unlocked_until"] if row else "") or "")
        except Exception:
            until = ""
    return {
        "lockRequired": required,
        "hasOwnerPhone": bool(phone),
        "unlocked": unlocked if required else True,
        "unlockedUntil": until if required and unlocked else "",
        "phoneMasked": mask_phone(phone) if phone else "",
        "emailMasked": mask_email(email) if email else "",
        "smsConfigured": sms_configured(),
        "unlockTtlMinutes": unlock_ttl_minutes(),
    }


def _resolve_company_id_for_request(data: dict | None = None) -> str:
    data = data or {}
    try:
        from backend.app.domains.shared import company_id_from_user

        cid = company_id_from_user(allow_query=True)
        if cid:
            return str(cid)
    except Exception:
        pass
    role = str((getattr(g, "current_user", None) or {}).get("role") or "")
    if role == "superadmin":
        return str(
            data.get("company_id")
            or request.args.get("company_id")
            or request.args.get("companyId")
            or ""
        ).strip()
    return str((getattr(g, "current_user", None) or {}).get("company_id") or "").strip()


def require_contracts_unlocked(handler):
    """Decorator: block salary/contract APIs when owner lock is active and session locked."""

    @wraps(handler)
    def wrapper(*args, **kwargs):
        from backend.app.domains.shared import forbidden_company
        from backend.server import get_db

        data = request.get_json(silent=True) if request.method in {"POST", "PUT", "PATCH", "DELETE"} else None
        cid = _resolve_company_id_for_request(data if isinstance(data, dict) else {})
        if not cid:
            return forbidden_company()
        db = get_db()
        if contracts_lock_required(db, cid) and not is_contracts_unlocked(db, getattr(g, "token", ""), cid):
            return (
                jsonify(
                    {
                        "error": "contracts_locked",
                        "stepUpRequired": True,
                        "message": (
                            "Owner-Freischaltung nötig (Verträge / sensible Exporte). "
                            "Bitte Code per SMS/E-Mail bestätigen."
                        ),
                    }
                ),
                403,
            )
        return handler(*args, **kwargs)

    return wrapper


# Shared owner step-up for contracts + sensitive exports / payroll.
require_owner_step_up = require_contracts_unlocked
