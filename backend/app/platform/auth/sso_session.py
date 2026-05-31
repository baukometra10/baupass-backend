"""Shared session bootstrap after enterprise SSO (Entra, SAML, Keycloak)."""
from __future__ import annotations

import secrets
from typing import Any

from flask import Response, redirect


def app_redirect_url() -> str:
    import os
    from flask import request

    return (os.getenv("BAUPASS_APP_URL") or os.getenv("BAUPASS_PUBLIC_URL") or request.url_root).rstrip("/")


def complete_admin_sso_login(user: Any, *, provider: str) -> Response:
    """Create session cookie and redirect to app after IdP login."""
    from backend.server import (
        SESSION_COOKIE_NAME,
        expiry_iso,
        get_db,
        is_request_secure,
        log_audit,
        row_to_dict,
        run_db_write_with_retry,
        should_use_cross_site_cookie,
    )

    db = get_db()
    token = secrets.token_urlsafe(24)

    def _persist():
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
        db.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user["id"], expiry_iso()),
        )
        db.commit()

    run_db_write_with_retry(_persist)

    log_audit(
        "login.success",
        f"{provider} SSO login for {user['username']}",
        target_type="user",
        target_id=user["id"],
        actor=row_to_dict(user),
        company_id=user["company_id"],
    )

    response = redirect(f"{app_redirect_url()}/?sso_ok=1&provider={provider}")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="None" if should_use_cross_site_cookie() else "Lax",
        secure=is_request_secure(),
        max_age=60 * 60 * 24 * 7,
    )
    return response


def find_admin_user_by_email(db, email: str):
    return db.execute(
        "SELECT * FROM users WHERE lower(COALESCE(email, '')) = ? AND role IN ('superadmin', 'company-admin')",
        (email.strip().lower(),),
    ).fetchone()
