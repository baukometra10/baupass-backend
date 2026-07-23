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
_OTP_REQUEST_MIN_SECONDS = 45
_OTP_REQUEST_MAX_PER_HOUR = 8
_STEP_UP_PURPOSE = "owner"

# Process-local fallback only if DB table is missing (legacy/dev).
_fail_counts: dict[str, tuple[int, float]] = {}
_otp_store: dict[str, tuple[str, float]] = {}
_delivery_fail_counts: dict[str, int] = {}


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
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS step_up_otp_requests (
                purpose TEXT NOT NULL,
                company_id TEXT NOT NULL,
                last_request_at TEXT NOT NULL DEFAULT '',
                window_started_at TEXT NOT NULL DEFAULT '',
                window_count INTEGER NOT NULL DEFAULT 0,
                delivery_fail_streak INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (purpose, company_id)
            )
            """
        )
        db.commit()
    except Exception as exc:
        _log.warning("ensure_step_up_tables failed: %s", exc)


def owner_step_up_enforced() -> bool:
    """When true, owner phone setup is mandatory before contracts/exports."""
    raw = str(os.getenv("BAUPASS_OWNER_STEP_UP_ENFORCE", "")).strip().lower()
    if raw in {"0", "false", "off", "no"}:
        return False
    if raw in {"1", "true", "on", "yes"}:
        return True
    env = str(os.getenv("BAUPASS_ENV", "")).strip().lower()
    if env in {"testing", "test", "dev", "development"}:
        return False
    try:
        from flask import current_app

        if current_app and current_app.config.get("TESTING"):
            return False
    except Exception:
        pass
    # Production / staging default: enforce.
    return True


def otp_request_min_seconds() -> int:
    raw = str(os.getenv("BAUPASS_OWNER_OTP_MIN_SECONDS", str(_OTP_REQUEST_MIN_SECONDS))).strip()
    try:
        return max(5, min(600, int(raw)))
    except ValueError:
        return _OTP_REQUEST_MIN_SECONDS


def otp_request_max_per_hour() -> int:
    raw = str(os.getenv("BAUPASS_OWNER_OTP_MAX_PER_HOUR", str(_OTP_REQUEST_MAX_PER_HOUR))).strip()
    try:
        return max(1, min(60, int(raw)))
    except ValueError:
        return _OTP_REQUEST_MAX_PER_HOUR


def assert_otp_request_allowed(db, company_id: str) -> None:
    """Throttle OTP issuance (min interval + hourly cap for successful sends)."""
    ensure_step_up_tables(db)
    cid = str(company_id)
    now = _now()
    now_iso = _now_iso()
    min_seconds = otp_request_min_seconds()
    max_per_hour = otp_request_max_per_hour()
    streak = 0
    try:
        row = db.execute(
            """
            SELECT last_request_at, window_started_at, window_count, delivery_fail_streak
            FROM step_up_otp_requests
            WHERE purpose = ? AND company_id = ?
            """,
            (_STEP_UP_PURPOSE, cid),
        ).fetchone()
    except Exception:
        row = None

    window_started = now_iso
    window_count = 0
    if row:
        streak = int(row["delivery_fail_streak"] or 0)
        last = str(row["last_request_at"] or "").strip()
        window_started = str(row["window_started_at"] or "").strip() or now_iso
        window_count = int(row["window_count"] or 0)
        if last:
            try:
                last_dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                delta = int((now - last_dt).total_seconds())
                if delta < min_seconds:
                    raise ValueError(f"rate_limited:{max(1, min_seconds - delta)}")
            except ValueError as exc:
                if str(exc).startswith("rate_limited:"):
                    raise
        try:
            win_dt = datetime.strptime(window_started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if (now - win_dt).total_seconds() >= 3600:
                window_started = now_iso
                window_count = 0
            elif window_count >= max_per_hour:
                # Failed Twilio/SMTP attempts should not lock the company for a full hour.
                if streak >= 1:
                    window_started = now_iso
                    window_count = 0
                else:
                    retry = max(1, int(3600 - (now - win_dt).total_seconds()))
                    raise ValueError(f"rate_limited:{retry}")
        except ValueError as exc:
            if str(exc).startswith("rate_limited:"):
                raise
            window_started = now_iso
            window_count = 0

    # Update last_request_at for min-interval; window_count rises only on successful delivery.
    db.execute(
        "DELETE FROM step_up_otp_requests WHERE purpose = ? AND company_id = ?",
        (_STEP_UP_PURPOSE, cid),
    )
    db.execute(
        """
        INSERT INTO step_up_otp_requests
            (purpose, company_id, last_request_at, window_started_at, window_count, delivery_fail_streak)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (_STEP_UP_PURPOSE, cid, now_iso, window_started, window_count, streak),
    )
    db.commit()


def record_otp_delivery_result(db, company_id: str, *, delivered: bool) -> int:
    """Track consecutive OTP delivery failures; count successful sends toward hourly cap."""
    ensure_step_up_tables(db)
    cid = str(company_id)
    streak = 0
    try:
        row = db.execute(
            """
            SELECT delivery_fail_streak, last_request_at, window_started_at, window_count
            FROM step_up_otp_requests
            WHERE purpose = ? AND company_id = ?
            """,
            (_STEP_UP_PURPOSE, cid),
        ).fetchone()
    except Exception:
        row = None
    if row:
        streak = int(row["delivery_fail_streak"] or 0)
        streak = 0 if delivered else streak + 1
        window_started = str(row["window_started_at"] or _now_iso())
        window_count = int(row["window_count"] or 0)
        if delivered:
            try:
                win_dt = datetime.strptime(window_started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if (_now() - win_dt).total_seconds() >= 3600:
                    window_started = _now_iso()
                    window_count = 0
            except Exception:
                window_started = _now_iso()
                window_count = 0
            window_count += 1
        db.execute(
            "DELETE FROM step_up_otp_requests WHERE purpose = ? AND company_id = ?",
            (_STEP_UP_PURPOSE, cid),
        )
        db.execute(
            """
            INSERT INTO step_up_otp_requests
                (purpose, company_id, last_request_at, window_started_at, window_count, delivery_fail_streak)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _STEP_UP_PURPOSE,
                cid,
                str(row["last_request_at"] or _now_iso()),
                window_started,
                window_count,
                streak,
            ),
        )
        db.commit()
    else:
        streak = 0 if delivered else 1
        _delivery_fail_counts[cid] = streak
        return streak
    if not delivered and streak >= 3:
        try:
            from backend.server import create_system_alert, get_db

            create_system_alert(
                db if db is not None else get_db(),
                code=f"step_up_otp_delivery_{cid}",
                severity="warning",
                message=f"Owner-OTP Zustellung fehlgeschlagen ({streak}×) für Firma {cid}.",
                details={"companyId": cid, "streak": streak},
                dedup_minutes=180,
            )
        except Exception as exc:
            _log.warning("otp delivery alert failed: %s", exc)
    return streak


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
    """Active when owner phone is set, or when enforcement requires setup."""
    if company_owner_phone(db, company_id):
        return True
    return owner_step_up_enforced()


def owner_setup_required(db, company_id: str) -> bool:
    return owner_step_up_enforced() and not bool(company_owner_phone(db, company_id))


def is_contracts_unlocked(db, token: str | None, company_id: str) -> bool:
    if owner_setup_required(db, company_id):
        return False
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


def otp_debug_delivery_allowed() -> bool:
    """Allow returning OTP in API response when channels are unavailable (local/dev only)."""
    raw = str(os.getenv("BAUPASS_OWNER_OTP_ALLOW_DEBUG", "")).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    env = str(os.getenv("BAUPASS_ENV", "")).strip().lower()
    if env in {"testing", "test", "dev", "development", "local"}:
        return True
    try:
        from flask import current_app

        if current_app and (current_app.config.get("TESTING") or current_app.debug):
            return True
    except Exception:
        pass
    return False


def resolve_otp_email(db, company_id: str, preferred: str = "") -> str:
    """Pick best available email for OTP delivery."""
    candidates = [
        str(preferred or "").strip().lower(),
        company_owner_email(db, company_id),
    ]
    try:
        user = getattr(g, "current_user", None) or {}
        candidates.append(str(user.get("email") or "").strip().lower())
    except Exception:
        pass
    try:
        row = db.execute(
            "SELECT contact, billing_email, contract_owner_email FROM companies WHERE id = ?",
            (str(company_id),),
        ).fetchone()
        if row:
            keys = set(row.keys()) if hasattr(row, "keys") else set()
            for key in ("contract_owner_email", "billing_email", "contact"):
                if key in keys:
                    candidates.append(str(row[key] or "").strip().lower())
    except Exception:
        pass
    for value in candidates:
        if value and "@" in value and " " not in value:
            return value
    return ""


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
    email_err = ""
    channels: list[str] = []
    body = f"SUPPIX Vertragszugang: Ihr Code lautet {code}. Gueltig {_OTP_TTL_MINUTES} Minuten."

    if phone and sms_configured():
        sms_ok, sms_err = send_sms(to=phone, body=body)
        if sms_ok:
            channels.append("sms")
        elif not sms_err:
            sms_err = "sms_send_failed"
    elif phone and not sms_configured():
        sms_err = "sms_not_configured"
    elif not phone:
        sms_err = "phone_missing"

    target_email = resolve_otp_email(db, company_id, preferred=email)
    if target_email:
        try:
            from backend.server import _send_otp_email_to_user

            email_ok = bool(
                _send_otp_email_to_user(
                    db,
                    {"email": target_email, "username": "contracts-owner"},
                    code,
                )
            )
            if email_ok:
                channels.append("email")
            else:
                email_err = "email_send_failed"
        except Exception as exc:
            email_err = str(exc)[:160] or "email_exception"
            _log.warning("contracts otp email failed: %s", exc)
    else:
        email_err = "email_missing"

    if not channels:
        # Dev fallback: keep code in logs when neither channel works.
        _log.warning(
            "contracts OTP for company %s could not be delivered (sms=%s email=%s). code=%s",
            company_id,
            sms_err or sms_ok,
            email_err or email_ok,
            code,
        )
    return {
        "channels": channels,
        "smsOk": sms_ok,
        "smsError": sms_err,
        "emailOk": email_ok,
        "emailError": email_err,
        "email": target_email,
        "smsConfigured": sms_configured(),
        "providerAccepted": bool(channels),
        "note": (
            "Provider accepted the message. Inbox/SMS arrival still depends on Brevo "
            "sender verification, spam filters, and SMS credits — check Brevo Transactional logs."
            if channels
            else ""
        ),
    }


def lock_status(db, *, company_id: str, token: str | None) -> dict[str, Any]:
    from backend.app.platform.notifications.sms import sms_configured

    phone = company_owner_phone(db, company_id)
    email = company_owner_email(db, company_id)
    enforced = owner_step_up_enforced()
    setup_needed = enforced and not bool(phone)
    required = bool(phone) or enforced
    unlocked = is_contracts_unlocked(db, token, company_id)
    until = ""
    if unlocked and token and required and not setup_needed:
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
        "setupEnforced": enforced,
        "ownerSetupRequired": setup_needed,
        "hasOwnerPhone": bool(phone),
        "unlocked": False if setup_needed else (unlocked if required else True),
        "unlockedUntil": until if required and unlocked and not setup_needed else "",
        "phoneMasked": mask_phone(phone) if phone else "",
        "emailMasked": mask_email(email) if email else "",
        "smsConfigured": sms_configured(),
        "unlockTtlMinutes": unlock_ttl_minutes(),
        "otpRequestMinSeconds": otp_request_min_seconds(),
        "otpRequestMaxPerHour": otp_request_max_per_hour(),
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
        if owner_setup_required(db, cid):
            return (
                jsonify(
                    {
                        "error": "owner_setup_required",
                        "stepUpRequired": True,
                        "ownerSetupRequired": True,
                        "message": (
                            "Owner-Handynummer muss eingerichtet werden, "
                            "bevor Verträge oder sensible Exporte nutzbar sind."
                        ),
                    }
                ),
                403,
            )
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

_SALARY_FORM_KEYS = frozenset(
    {
        "salary_gross_monthly",
        "hourly_rate",
        "gross_monthly",
        "monthly_salary",
        "salary",
        "gross_salary",
        "bruttogehalt",
        "hourly_wage",
        "salary_hourly",
        "salary_type",
    }
)
_REDACTED_MARK = "••••"


def sensitive_fields_locked(db, company_id: str, token: str | None) -> bool:
    """True when salary/body should be redacted (lock active, session not unlocked)."""
    if owner_setup_required(db, company_id):
        return True
    if not contracts_lock_required(db, company_id):
        return False
    return not is_contracts_unlocked(db, token, company_id)


def _redact_form_dict(form: dict[str, Any]) -> dict[str, Any]:
    out = dict(form or {})
    for key in list(out.keys()):
        if key in _SALARY_FORM_KEYS or "salary" in key.lower() or "lohn" in key.lower() or "hourly" in key.lower():
            if out.get(key) not in (None, ""):
                out[key] = _REDACTED_MARK
    return out


def redact_contract_record(contract: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip salary fields and contract body when step-up is locked."""
    if not contract:
        return contract
    item = dict(contract)
    item["salaryRedacted"] = True
    item["bodyRedacted"] = True
    # Hide full contract body (salary is embedded in prose).
    if item.get("draft_text"):
        item["draft_text"] = ""
    if item.get("final_text"):
        item["final_text"] = ""
    if item.get("ai_prompt"):
        item["ai_prompt"] = ""
    # Redact structured form inside input_json
    raw = item.get("input_json")
    parsed: Any = raw
    if isinstance(raw, str) and raw.strip():
        try:
            import json as _json

            parsed = _json.loads(raw)
        except Exception:
            parsed = {}
    if isinstance(parsed, dict):
        form = parsed.get("form") if isinstance(parsed.get("form"), dict) else parsed
        if isinstance(form, dict):
            redacted_form = _redact_form_dict(form)
            if "form" in parsed:
                parsed = {**parsed, "form": redacted_form}
            else:
                parsed = redacted_form
        try:
            import json as _json

            item["input_json"] = _json.dumps(parsed, ensure_ascii=False)
        except Exception:
            item["input_json"] = "{}"
        item["form"] = parsed.get("form") if isinstance(parsed, dict) and isinstance(parsed.get("form"), dict) else parsed
    # Common enriched keys
    for key in list(item.keys()):
        if key in _SALARY_FORM_KEYS:
            item[key] = _REDACTED_MARK
    return item


def require_owner_setup_complete(handler):
    """Block only when owner phone setup is still mandatory."""

    @wraps(handler)
    def wrapper(*args, **kwargs):
        from backend.app.domains.shared import forbidden_company
        from backend.server import get_db

        data = request.get_json(silent=True) if request.method in {"POST", "PUT", "PATCH", "DELETE"} else None
        cid = _resolve_company_id_for_request(data if isinstance(data, dict) else {})
        if not cid:
            return forbidden_company()
        db = get_db()
        if owner_setup_required(db, cid):
            return (
                jsonify(
                    {
                        "error": "owner_setup_required",
                        "stepUpRequired": True,
                        "ownerSetupRequired": True,
                        "message": (
                            "Owner-Handynummer muss eingerichtet werden, "
                            "bevor Verträge nutzbar sind."
                        ),
                    }
                ),
                403,
            )
        return handler(*args, **kwargs)

    return wrapper
