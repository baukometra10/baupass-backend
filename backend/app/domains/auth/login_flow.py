"""Admin login flow — credentials, OTP/2FA, session cookie (extracted from server.py)."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
from flask import jsonify, request


def _user_value(user, key: str, default=None):
    if hasattr(user, "keys") and key in user.keys():
        value = user[key]
        return default if value is None and default is not None else value
    return default


def _password_hash_matches(srv, stored_hash: str, password: str) -> bool:
    stored_hash = str(stored_hash or "").strip()
    if not stored_hash.startswith(("pbkdf2:", "scrypt:")):
        return False
    try:
        return bool(srv.check_password_hash(stored_hash, password))
    except Exception:
        return False


def _schema_error_message(exc: Exception) -> bool:
    message = str(exc).lower()
    if "not login-ready" in message or "sessions table missing" in message:
        return True
    if "no such table" in message or "does not exist" in message:
        return True
    if "database is locked" in message or "readonly" in message or "disk" in message:
        return True
    try:
        from backend.app.db.pg_bootstrap import is_schema_error

        return bool(is_schema_error(exc))
    except ImportError:
        return False


def _verify_totp_code(secret: str, otp_code: str) -> bool:
    secret = str(secret or "").strip()
    otp_code = str(otp_code or "").strip()
    if not secret or not otp_code:
        return False
    try:
        return bool(pyotp.TOTP(secret).verify(otp_code, valid_window=1))
    except Exception:
        return False


def _safe_log_audit(srv, event_type: str, message: str, **kwargs) -> None:
    try:
        srv.log_audit(event_type, message, **kwargs)
    except Exception as exc:
        srv.app.logger.warning("[login] audit skipped for %s: %s", event_type, exc)


def perform_login():
    """Run POST /api/login; returns Flask response or (json, status)."""
    import backend.server as srv

    def login_error(code, status_code=200, **extra):
        payload = {"ok": False, "error": code}
        payload.update(extra)
        return jsonify(payload), status_code

    try:
        return _perform_login_core(srv, login_error)
    except Exception as exc:
        if _schema_error_message(exc):
            try:
                from backend.app.db.schema_errors import database_not_ready_response

                return database_not_ready_response(ok_field=True)
            except ImportError:
                pass
        srv.app.logger.exception("admin login failed unexpectedly")
        return login_error(
            "login_server_error",
            200,
            message="Anmeldung voruebergehend nicht moeglich. Bitte erneut versuchen.",
        )


def _log_login_failed(srv, username: str, reason: str = "") -> None:
    try:
        ip = srv.get_client_ip()
        suffix = f" ip:{ip}" if ip else ""
        detail = f" ({reason})" if reason else ""
        srv.log_audit(
            "login.failed",
            f"Fehlgeschlagener Login fuer {username or 'unbekannt'}{suffix}{detail}",
        )
    except Exception:
        srv.app.logger.warning("login.failed audit skipped", exc_info=True)


def _perform_login_core(srv, login_error):
    """Run POST /api/login; returns Flask response or (json, status)."""
    from backend.app.db.schema_errors import guard_core_schema

    blocked = guard_core_schema(ok_field=True)
    if blocked is not None:
        return blocked

    client_ip = srv.get_client_ip()
    try:
        from backend.app.platform.guardian.security import is_ip_banned

        if is_ip_banned(srv.get_db(), client_ip):
            return login_error(
                "ip_blocked",
                403,
                message="Zugriff von dieser IP voruebergehend gesperrt.",
            )
    except Exception:
        pass

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
        if _schema_error_message(exc):
            try:
                from backend.app.db.schema_errors import database_not_ready_response

                return database_not_ready_response(ok_field=True)
            except ImportError:
                pass
        raise

    if not user:
        srv.register_login_failure(throttle_key)
        _log_login_failed(srv, username)
        return login_error("invalid_credentials")

    stored_hash = str(_user_value(user, "password_hash", "") or "").strip()
    hash_ok = _password_hash_matches(srv, stored_hash, password)
    if not hash_ok:
        srv.register_login_failure(throttle_key)
        _log_login_failed(srv, username)
        return login_error("invalid_credentials")

    required_role_by_scope = {
        "server-admin": "superadmin",
        "company-admin": "company-admin",
        "turnstile": "turnstile",
    }
    required_role = required_role_by_scope.get(login_scope)
    if required_role and user["role"] != required_role:
        srv.register_login_failure(throttle_key)
        _log_login_failed(srv, username, "scope_mismatch")
        return login_error("login_scope_mismatch")

    twofa_enabled = int(_user_value(user, "twofa_enabled", 0) or 0) == 1
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
            _safe_log_audit(
                srv,
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

                try:
                    srv.run_db_write_with_retry(_persist_otp_code)
                except Exception as exc:
                    if _schema_error_message(exc):
                        from backend.app.db.schema_errors import database_not_ready_response

                        return database_not_ready_response(ok_field=True)
                    raise
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
            secret = str(_user_value(user, "twofa_secret", "") or "").strip()
            if not _verify_totp_code(secret, otp_code):
                srv.register_login_failure(throttle_key)
                return login_error("otp_invalid")

    if not srv.is_tenant_host_valid(db, srv.row_to_dict(user)):
        srv.register_login_failure(throttle_key)
        return login_error("forbidden_tenant_host")

    if user["role"] != "superadmin":
        company_error = srv.get_company_access_error(db, user["company_id"])
        if company_error:
            _safe_log_audit(
                srv,
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
        except Exception as exc:
            message = str(exc).lower()
            legacy_schema = (
                "no such column" in message
                or "has no column named" in message
                or ("column" in message and "does not exist" in message)
            )
            missing_sessions = "no such table" in message and "sessions" in message
            if missing_sessions:
                raise RuntimeError("sessions table missing") from exc
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
    _safe_log_audit(
        srv,
        "login.success",
        login_message,
        target_type="user",
        target_id=user["id"],
        actor=srv.row_to_dict(user),
        company_id=user["company_id"],
    )

    try:
        from backend.app.domains.admin.survey_dispatch import maybe_send_survey_invite_on_login

        maybe_send_survey_invite_on_login(db, srv.row_to_dict(user))
    except Exception:
        pass

    response_user = srv.row_to_dict(user)
    response_user["support_read_only"] = bool(support_read_only)
    response_user["support_company_name"] = support_company_name
    response_user["support_actor_name"] = support_actor_name
    try:
        serialized_user = srv.serialize_user(response_user)
    except Exception as exc:
        srv.app.logger.warning("[login] serialize_user failed: %s", exc)
        serialized_user = {
            "id": str(_user_value(user, "id", "")),
            "username": str(_user_value(user, "username", "")),
            "name": str(_user_value(user, "name", "")),
            "role": str(_user_value(user, "role", "")),
            "company_id": _user_value(user, "company_id"),
            "twofa_enabled": int(_user_value(user, "twofa_enabled", 0) or 0) == 1,
            "email": str(_user_value(user, "email", "") or ""),
            "support_read_only": bool(support_read_only),
            "support_company_name": support_company_name,
            "support_actor_name": support_actor_name,
            "preview_company_id": "",
        }
    response = jsonify({"ok": True, "token": token, "user": serialized_user})
    response.set_cookie(
        srv.SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="None" if srv.should_use_cross_site_cookie() else "Lax",
        secure=srv.is_request_secure(),
    )
    return response
