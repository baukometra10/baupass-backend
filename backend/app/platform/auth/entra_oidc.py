"""Optional Microsoft Entra ID (Azure AD) SSO for WorkPass admin users."""
from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from flask import Flask, jsonify, redirect, request

# state -> marker in-memory (single-instance); use Redis for multi-replica if needed
def entra_config() -> dict[str, str] | None:
    tenant = (os.getenv("BAUPASS_ENTRA_TENANT_ID") or os.getenv("AZURE_TENANT_ID") or "").strip()
    client_id = (os.getenv("BAUPASS_ENTRA_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("BAUPASS_ENTRA_CLIENT_SECRET") or os.getenv("AZURE_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.getenv("BAUPASS_ENTRA_REDIRECT_URI") or "").strip()
    if not (tenant and client_id and client_secret and redirect_uri):
        return None
    return {
        "tenant": tenant,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


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


def register_entra_auth_routes(flask_app: Flask) -> None:
    @flask_app.get("/api/auth/entra/status")
    def entra_status():
        cfg = entra_config()
        return jsonify(
            {
                "configured": bool(cfg),
                "tenantId": cfg["tenant"] if cfg else None,
                "loginPath": "/api/auth/entra/start" if cfg else None,
            }
        )

    @flask_app.get("/api/auth/entra/start")
    def entra_start():
        cfg = entra_config()
        if not cfg:
            return jsonify({"ok": False, "error": "entra_not_configured"}), 503
        from .sso_state import issue_oidc_state

        state = issue_oidc_state()
        params = {
            "client_id": cfg["client_id"],
            "response_type": "code",
            "redirect_uri": cfg["redirect_uri"],
            "response_mode": "query",
            "scope": "openid profile email User.Read",
            "state": state,
        }
        url = (
            f"https://login.microsoftonline.com/{urllib.parse.quote(cfg['tenant'])}/oauth2/v2.0/authorize?"
            + urllib.parse.urlencode(params)
        )
        return redirect(url)

    @flask_app.get("/api/auth/entra/callback")
    def entra_callback():
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

        cfg = entra_config()
        if not cfg:
            return jsonify({"ok": False, "error": "entra_not_configured"}), 503

        err = request.args.get("error")
        if err:
            return redirect(f"{_app_redirect_url()}/?entra_error={urllib.parse.quote(err)}")

        code = (request.args.get("code") or "").strip()
        state = (request.args.get("state") or "").strip()
        from .sso_state import consume_oidc_state

        if not code or not consume_oidc_state(state):
            return redirect(f"{_app_redirect_url()}/?entra_error=invalid_state")

        token_url = f"https://login.microsoftonline.com/{cfg['tenant']}/oauth2/v2.0/token"
        try:
            token_resp = _http_form_post(
                token_url,
                {
                    "client_id": cfg["client_id"],
                    "client_secret": cfg["client_secret"],
                    "code": code,
                    "redirect_uri": cfg["redirect_uri"],
                    "grant_type": "authorization_code",
                },
            )
        except (urllib.error.URLError, json.JSONDecodeError, ValueError):
            return redirect(f"{_app_redirect_url()}/?entra_error=token_exchange_failed")

        access_token = str(token_resp.get("access_token") or "")
        if not access_token:
            return redirect(f"{_app_redirect_url()}/?entra_error=no_access_token")

        try:
            profile = _http_get_json(
                "https://graph.microsoft.com/v1.0/me",
                {"Authorization": f"Bearer {access_token}"},
            )
        except (urllib.error.URLError, json.JSONDecodeError, ValueError):
            return redirect(f"{_app_redirect_url()}/?entra_error=graph_failed")

        email = str(profile.get("mail") or profile.get("userPrincipalName") or "").strip().lower()
        if not email:
            return redirect(f"{_app_redirect_url()}/?entra_error=no_email")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE lower(COALESCE(email, '')) = ? AND role IN ('superadmin', 'company-admin')",
            (email,),
        ).fetchone()
        if not user:
            return redirect(f"{_app_redirect_url()}/?entra_error=user_not_linked")

        token = secrets.token_urlsafe(24)

        def _persist():
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
            db.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user["id"], expiry_iso()),
            )
            db.commit()

        run_db_write_with_retry(_persist)

        try:
            from backend.app.platform.rbac.enforcement import apply_entra_group_roles

            groups_resp = _http_get_json(
                "https://graph.microsoft.com/v1.0/me/memberOf?$select=id",
                {"Authorization": f"Bearer {access_token}"},
            )
            group_ids = [
                str(gobj.get("id") or "")
                for gobj in (groups_resp.get("value") or [])
                if gobj.get("id")
            ]
            apply_entra_group_roles(db, str(user["id"]), str(user["company_id"] or "") or None, group_ids)
        except Exception:
            pass

        log_audit(
            "login.success",
            f"Entra SSO login for {user['username']}",
            target_type="user",
            target_id=user["id"],
            actor=row_to_dict(user),
            company_id=user["company_id"],
        )

        response = redirect(f"{_app_redirect_url()}/?entra_ok=1")
        response.set_cookie(
            SESSION_COOKIE_NAME,
            token,
            httponly=True,
            samesite="None" if should_use_cross_site_cookie() else "Lax",
            secure=is_request_secure(),
            max_age=60 * 60 * 24 * 7,
        )
        return response
