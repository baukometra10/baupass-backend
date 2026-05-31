"""Admin login flow — credentials, OTP/2FA, session cookie (extracted from server.py)."""
from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

import pyotp
from flask import jsonify, request


def perform_login():
    """Run POST /api/login; returns Flask response or (json, status)."""
    import backend.server as srv

    def login_error(code, status_code=200, **extra):
        payload = {"ok": False, "error": code}
        payload.update(extra)
        return jsonify(payload), status_code

    from backend.app.db.schema_errors import guard_core_schema

    blocked = guard_core_schema(ok_field=True)
    if blocked is not None:
        return blocked

    throttle_key = srv.build_login_throttle_key()
    allowed, retry_after = srv.can_attempt_login(throttle_key)
    if not allowed:
        return login_error("too_many_attempts", 429, retryAfterSeconds=retry_after)

    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip().lower()
    password = payload.get("password") or ""
    if not username or not str(password).strip():
        srv.register_login_failure(throttle_key)
        return login_error("invalid_credentials")
    otp_code = (payload.get("otpCode") or "").strip()
    login_scope = (payload.get("loginScope") or "auto").strip().lower()
    support_company_id = (payload.get("supportCompanyId") or "").strip()
    support_actor_name = (payload.get("supportActorName") or "").strip()

    try:
        db = srv.get_db()
        user = db.execute("SELECT * FROM users WHERE lower(username) = ?", (username,)).fetchone()
    except Exception as exc:
        try:
            from backend.app.db.pg_bootstrap import is_schema_error
            from backend.app.db.schema_errors import database_not_ready_response

            if is_schema_error(exc):
                return database_not_ready_response(ok_field=True)
        except ImportError:
            pass
        raise

    if not user:
        srv.register_login_failure(throttle_key)
        srv.log_audit("login.failed", f"Fehlgeschlagener Login fuer {username or 'unbekannt'}")
        return login_error("invalid_credentials")

    stored_hash = str(user["password_hash"] or "").strip()
    hash_ok = bool(
        stored_hash.startswith(("pbkdf2:", "scrypt:"))
        and srv.check_password_hash(stored_hash, password)
    )
    if not hash_ok:
        srv.register_login_failure(throttle_key)
        srv.log_audit("login.failed", f"Fehlgeschlagener Login fuer {username or 'unbekannt'}")
        return login_error("invalid_credentials")

    required_role_by_scope = {
        "server-admin": "superadmin",
        "company-admin": "company-admin",
        "turnstile": "turnstile",
    }
    required_role = required_role_by_scope.get(login_scope)
    if required_role and user["role"] != required_role:
        srv.register_login_failure(throttle_key)
        srv.log_audit("login.failed", f"Login-Typ passt nicht zu {username or 'unbekannt'}")
        return login_error("login_scope_mismatch")

    twofa_enabled = int(user["twofa_enabled"]) == 1
    turnstile_auto_2fa = user["role"] == "turnstile"
    if srv.REQUIRE_SUPERADMIN_2FA and user["role"] == "superadmin" and not twofa_enabled:
        user_keys = set(user.keys()) if hasattr(user, "keys") else set()
        user_email = (user["email"] if "email" in user_keys else "").strip().lower()
        setup_email = srv.clean_text_input(payload.get("setupEmail") or "", max_len=200).strip().lower()
        if setup_email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", setup_email):
            return login_error("invalid_setup_email", message="Bitte eine gueltige E-Mail-Adresse eingeben.")
        target_email = setup_email or user_email
        if target_email:

            def _bootstrap_superadmin_twofa():
                db.execute(
                    "UPDATE users SET email = ?, twofa_enabled = 1 WHERE id = ?",
                    (target_email, user["id"]),
                )
                db.commit()

            srv.run_db_write_with_retry(_bootstrap_superadmin_twofa)
            user = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
            twofa_enabled = True
            srv.log_audit(
                "security.superadmin_2fa_bootstrapped",
                f"Superadmin 2FA (E-Mail-OTP) beim Login vorbereitet: {username}",
                target_type="user",
                target_id=user["id"],
            )
        else:
            return login_error(
                "superadmin_setup_email_required",
                message="Superadmin: Bitte E-Mail fuer OTP eingeben und erneut anmelden (einmalige Einrichtung).",
            )
    if twofa_enabled and not turnstile_auto_2fa:
        user_keys = set(user.keys()) if hasattr(user, "keys") else set()
        user_email = (user["email"] if "email" in user_keys else "").strip()

        if not otp_code:
            if user_email:
                cooldown_threshold = (datetime.now(timezone.utc) + timedelta(seconds=540)).isoformat()
                recent_otp = db.execute(
                    "SELECT id FROM otp_codes WHERE user_id = ? AND expires_at > ?",
                    (user["id"], cooldown_threshold),
                ).fetchone()
                if recent_otp:
                    srv.clear_login_failures(throttle_key)
                    return login_error("otp_sent")

                otp = str(secrets.randbelow(900000) + 100000)
                otp_id = secrets.token_urlsafe(16)
                expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

                def _persist_otp_code():
                    db.execute("DELETE FROM otp_codes WHERE user_id = ?", (user["id"],))
                    db.execute(
                        "INSERT INTO otp_codes (id, user_id, code, expires_at) VALUES (?,?,?,?)",
                        (otp_id, user["id"], otp, expires),
                    )
                    db.commit()

                srv.run_db_write_with_retry(_persist_otp_code)
                sent = srv._send_otp_email_to_user(db, user, otp)
                if not sent:
                    srv.app.logger.warning(
                        f"[OTP-FALLBACK] Kein SMTP konfiguriert oder Versand fehlgeschlagen – "
                        f"OTP fuer Benutzer '{user['username']}': {otp}"
                    )
                srv.clear_login_failures(throttle_key)
                return login_error("otp_sent")
            srv.register_login_failure(throttle_key)
            return login_error("otp_required")
        now_str = datetime.now(timezone.utc).isoformat()
        otp_row = db.execute(
            "SELECT id FROM otp_codes WHERE user_id = ? AND code = ? AND expires_at > ?",
            (user["id"], otp_code, now_str),
        ).fetchone()
        if otp_row:
            db.execute("DELETE FROM otp_codes WHERE user_id = ?", (user["id"],))
            db.commit()
        else:
            secret = (user["twofa_secret"] or "").strip()
            if not (secret and pyotp.TOTP(secret).verify(otp_code, valid_window=1)):
                srv.register_login_failure(throttle_key)
                return login_error("otp_invalid")

    if not srv.is_tenant_host_valid(db, srv.row_to_dict(user)):
        srv.register_login_failure(throttle_key)
        return login_error("forbidden_tenant_host")

    if user["role"] != "superadmin":
        company_error = srv.get_company_access_error(db, user["company_id"])
        if company_error:
            srv.log_audit(
                "login.blocked",
                f"Login fuer {user['username']} wegen Firmensperre blockiert",
                target_type="company",
                target_id=user["company_id"],
            )
            return login_error(
                company_error["error"],
                companyStatus=company_error["companyStatus"],
                companyName=company_error["companyName"],
                message=company_error.get("message", ""),
            )

    support_read_only = 0
    support_company_name = ""
    if support_company_id:
        if user["role"] != "company-admin" or user["company_id"] != support_company_id:
            srv.register_login_failure(throttle_key)
            return login_error("support_company_mismatch")
        company_row = db.execute("SELECT id, name FROM companies WHERE id = ?", (support_company_id,)).fetchone()
        if not company_row:
            srv.register_login_failure(throttle_key)
            return login_error("company_not_found")
        support_read_only = 1
        support_company_name = company_row["name"] or ""

    srv.clear_login_failures(throttle_key)

    token = secrets.token_urlsafe(24)

    def _persist_login_session():
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
        try:
            db.execute(
                """
                INSERT INTO sessions (token, user_id, expires_at, support_read_only, support_company_name, support_actor_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (token, user["id"], srv.expiry_iso(), support_read_only, support_company_name, support_actor_name),
            )
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            legacy_schema = (
                "no such column" in message
                or "has no column named support_read_only" in message
                or "has no column named support_company_name" in message
                or "has no column named support_actor_name" in message
            )
            if not legacy_schema:
                raise
            db.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user["id"], srv.expiry_iso()),
            )
        db.commit()

    srv.run_db_write_with_retry(_persist_login_session)

    try:
        from backend.app.platform.security.session_devices import register_session_device

        register_session_device(db, token=token, user_id=user["id"], req=request)
    except Exception:
        pass

    login_message = f"Benutzer {user['username']} angemeldet"
    if support_read_only:
        actor_label = support_actor_name or "Support"
        login_message = (
            f"Support-Login fuer {support_company_name or user['username']} "
            f"gestartet durch {actor_label} (nur lesen)"
        )
    srv.log_audit(
        "login.success",
        login_message,
        target_type="user",
        target_id=user["id"],
        actor=srv.row_to_dict(user),
        company_id=user["company_id"],
    )

    response_user = srv.row_to_dict(user)
    response_user["support_read_only"] = bool(support_read_only)
    response_user["support_company_name"] = support_company_name
    response_user["support_actor_name"] = support_actor_name
    response = jsonify({"ok": True, "token": token, "user": srv.serialize_user(response_user)})
    response.set_cookie(
        srv.SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="None" if srv.should_use_cross_site_cookie() else "Lax",
        secure=srv.is_request_secure(),
    )
    return response
