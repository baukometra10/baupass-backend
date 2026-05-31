"""Keycloak / generic OIDC IdP (on-prem or cloud) for enterprise SSO."""
from __future__ import annotations

import json
import os
import secrets
import urllib.parse
import urllib.request
from typing import Any

from flask import Flask, jsonify, redirect, request

def keycloak_config() -> dict[str, str] | None:
    issuer = (os.getenv("BAUPASS_KEYCLOAK_ISSUER") or os.getenv("BAUPASS_OIDC_ISSUER") or "").strip().rstrip("/")
    client_id = (os.getenv("BAUPASS_KEYCLOAK_CLIENT_ID") or os.getenv("BAUPASS_OIDC_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("BAUPASS_KEYCLOAK_CLIENT_SECRET") or os.getenv("BAUPASS_OIDC_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.getenv("BAUPASS_KEYCLOAK_REDIRECT_URI") or os.getenv("BAUPASS_OIDC_REDIRECT_URI") or "").strip()
    if not (issuer and client_id and client_secret and redirect_uri):
        return None
    return {
        "issuer": issuer,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


def _app_redirect_url() -> str:
    return (os.getenv("BAUPASS_APP_URL") or os.getenv("BAUPASS_PUBLIC_URL") or request.url_root).rstrip("/")


def _http_form_post(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _oidc_endpoints(cfg: dict[str, str]) -> dict[str, str]:
    discovery = f"{cfg['issuer']}/.well-known/openid-configuration"
    doc = _http_get_json(discovery)
    return {
        "authorization_endpoint": doc["authorization_endpoint"],
        "token_endpoint": doc["token_endpoint"],
        "userinfo_endpoint": doc.get("userinfo_endpoint") or "",
    }


def register_keycloak_auth_routes(flask_app: Flask) -> None:
    @flask_app.get("/api/auth/keycloak/status")
    def keycloak_status():
        cfg = keycloak_config()
        return jsonify(
            {
                "configured": bool(cfg),
                "issuer": cfg["issuer"] if cfg else None,
                "loginPath": "/api/auth/keycloak/start" if cfg else None,
                "protocol": "oidc",
            }
        )

    @flask_app.get("/api/auth/keycloak/start")
    def keycloak_start():
        cfg = keycloak_config()
        if not cfg:
            return jsonify({"ok": False, "error": "keycloak_not_configured"}), 503
        endpoints = _oidc_endpoints(cfg)
        from .sso_state import issue_oidc_state

        state = issue_oidc_state()
        params = {
            "client_id": cfg["client_id"],
            "response_type": "code",
            "redirect_uri": cfg["redirect_uri"],
            "scope": "openid profile email",
            "state": state,
        }
        url = endpoints["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)
        return redirect(url)

    @flask_app.get("/api/auth/keycloak/callback")
    def keycloak_callback():
        from backend.server import (
            SESSION_COOKIE_NAME,
            expiry_iso,
            get_db,
            is_request_secure,
            log_audit,
            run_db_write_with_retry,
            should_use_cross_site_cookie,
        )

        cfg = keycloak_config()
        if not cfg:
            return jsonify({"ok": False, "error": "keycloak_not_configured"}), 503

        err = request.args.get("error")
        if err:
            return redirect(f"{_app_redirect_url()}/?keycloak_error={urllib.parse.quote(err)}")

        code = (request.args.get("code") or "").strip()
        state = (request.args.get("state") or "").strip()
        from .sso_state import consume_oidc_state

        if not code or not consume_oidc_state(state):
            return redirect(f"{_app_redirect_url()}/?keycloak_error=invalid_state")

        endpoints = _oidc_endpoints(cfg)
        token_payload = _http_form_post(
            endpoints["token_endpoint"],
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": cfg["redirect_uri"],
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
            },
        )
        access_token = token_payload.get("access_token") or ""
        email = ""
        if endpoints.get("userinfo_endpoint") and access_token:
            profile = _http_get_json(endpoints["userinfo_endpoint"], {"Authorization": f"Bearer {access_token}"})
            email = str(profile.get("email") or profile.get("preferred_username") or "").strip().lower()

        if not email:
            return redirect(f"{_app_redirect_url()}/?keycloak_error=missing_email")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE lower(email) = ?", (email,)).fetchone()
        if not user:
            return redirect(f"{_app_redirect_url()}/?keycloak_error=user_not_provisioned")

        token = secrets.token_urlsafe(24)

        def _persist():
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
            db.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user["id"], expiry_iso()),
            )
            db.commit()

        run_db_write_with_retry(_persist)
        log_audit("login.success", f"Keycloak SSO: {email}", target_type="user", target_id=user["id"], actor=None)

        response = redirect(f"{_app_redirect_url()}/?keycloak=1")
        response.set_cookie(
            SESSION_COOKIE_NAME,
            token,
            httponly=True,
            samesite="None" if should_use_cross_site_cookie() else "Lax",
            secure=is_request_secure(),
        )
        return response
