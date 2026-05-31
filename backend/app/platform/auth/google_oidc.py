"""Optional Google Workspace SSO for Control Pass admin users."""
from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from flask import Flask, jsonify, redirect, request

def google_config() -> dict[str, str] | None:
    client_id = (os.getenv("BAUPASS_GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("BAUPASS_GOOGLE_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.getenv("BAUPASS_GOOGLE_REDIRECT_URI") or "").strip()
    if not (client_id and client_secret and redirect_uri):
        return None
    return {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri}


def _app_redirect_url() -> str:
    return (os.getenv("BAUPASS_APP_URL") or os.getenv("BAUPASS_PUBLIC_URL") or request.url_root).rstrip("/")


def _http_form_post(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def register_google_auth_routes(flask_app: Flask) -> None:
    @flask_app.get("/api/auth/google/status")
    def google_status():
        cfg = google_config()
        return jsonify(
            {
                "configured": bool(cfg),
                "loginPath": "/api/auth/google/start" if cfg else None,
            }
        )

    @flask_app.get("/api/auth/google/start")
    def google_start():
        cfg = google_config()
        if not cfg:
            return jsonify({"ok": False, "error": "google_not_configured"}), 503
        from .sso_state import issue_oidc_state

        state = issue_oidc_state()
        params = {
            "client_id": cfg["client_id"],
            "response_type": "code",
            "redirect_uri": cfg["redirect_uri"],
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "select_account",
        }
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
        return redirect(url)

    @flask_app.get("/api/auth/google/callback")
    def google_callback():
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

        cfg = google_config()
        if not cfg:
            return jsonify({"ok": False, "error": "google_not_configured"}), 503

        err = request.args.get("error")
        if err:
            return redirect(f"{_app_redirect_url()}/?google_error={urllib.parse.quote(err)}")

        code = (request.args.get("code") or "").strip()
        state = (request.args.get("state") or "").strip()
        from .sso_state import consume_oidc_state

        if not code or not consume_oidc_state(state):
            return redirect(f"{_app_redirect_url()}/?google_error=invalid_state")

        try:
            token_resp = _http_form_post(
                "https://oauth2.googleapis.com/token",
                {
                    "client_id": cfg["client_id"],
                    "client_secret": cfg["client_secret"],
                    "code": code,
                    "redirect_uri": cfg["redirect_uri"],
                    "grant_type": "authorization_code",
                },
            )
        except (urllib.error.URLError, json.JSONDecodeError, ValueError):
            return redirect(f"{_app_redirect_url()}/?google_error=token_exchange_failed")

        access_token = str(token_resp.get("access_token") or "")
        if not access_token:
            return redirect(f"{_app_redirect_url()}/?google_error=no_access_token")

        try:
            profile = _http_get_json(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                {"Authorization": f"Bearer {access_token}"},
            )
        except (urllib.error.URLError, json.JSONDecodeError, ValueError):
            return redirect(f"{_app_redirect_url()}/?google_error=userinfo_failed")

        email = str(profile.get("email") or "").strip().lower()
        if not email:
            return redirect(f"{_app_redirect_url()}/?google_error=no_email")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE lower(COALESCE(email, '')) = ? AND role IN ('superadmin', 'company-admin')",
            (email,),
        ).fetchone()
        if not user:
            return redirect(f"{_app_redirect_url()}/?google_error=user_not_linked")

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
            f"Google SSO login for {user['username']}",
            target_type="user",
            target_id=user["id"],
            actor=row_to_dict(user),
            company_id=user["company_id"],
        )

        response = redirect(f"{_app_redirect_url()}/?google_ok=1")
        response.set_cookie(
            SESSION_COOKIE_NAME,
            token,
            httponly=True,
            samesite="None" if should_use_cross_site_cookie() else "Lax",
            secure=is_request_secure(),
            max_age=60 * 60 * 24 * 7,
        )
        return response
