"""Auth domain — login, 2FA, password reset, session (handlers in server until extracted)."""
from __future__ import annotations

from flask import Blueprint, Flask, g, jsonify

from .service import AuthService

auth_core_bp = Blueprint("auth_domain_core", __name__)
auth_v2_bp = Blueprint("auth_domain_v2", __name__)
_service = AuthService()


def _register_core_auth_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted

    if routes_already_mounted("auth_core"):
        return
    from backend.server import (
        activate_twofa,
        apply_password_reset,
        change_password,
        disable_twofa,
        emergency_disable_twofa,
        get_twofa_status,
        logout,
        me,
        request_password_reset,
        session_bootstrap,
        heartbeat,
        update_me_account,
        update_me_email,
    )

    def _login():
        return _service.login()

    rules = (
        ("/login", _login, ("POST",)),
        ("/logout", logout, ("POST",)),
        ("/session/bootstrap", session_bootstrap, ("GET",)),
        ("/me", me, ("GET",)),
        ("/me/heartbeat", heartbeat, ("POST",)),
        ("/me/email", update_me_email, ("PUT",)),
        ("/me/account", update_me_account, ("PUT",)),
        ("/me/password", change_password, ("POST",)),
        ("/me/2fa", get_twofa_status, ("GET",)),
        ("/me/2fa/activate", activate_twofa, ("POST",)),
        ("/me/2fa/disable", disable_twofa, ("POST",)),
        ("/emergency/disable-2fa", emergency_disable_twofa, ("POST",)),
        ("/auth/request-password-reset", request_password_reset, ("POST",)),
        ("/auth/reset-password/<raw_token>", apply_password_reset, ("POST",)),
    )
    for path, view_func, methods in rules:
        auth_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))
    mark_routes_mounted("auth_core")


def register_auth_blueprint(flask_app: Flask) -> None:
    from backend.server import get_db, require_auth

    _register_core_auth_routes()

    @auth_v2_bp.get("/auth/session")
    @require_auth
    def v2_session():
        return jsonify(
            {
                "user": {
                    "id": g.current_user.get("id"),
                    "username": g.current_user.get("username"),
                    "role": g.current_user.get("role"),
                    "company_id": g.current_user.get("company_id"),
                },
                "token_active": bool(getattr(g, "token", "")),
            }
        )

    @auth_v2_bp.post("/auth/revoke")
    @require_auth
    def v2_revoke():
        _service.logout(g.token, g.current_user)
        return jsonify({"ok": True})

    from .._routes import register_blueprint_once

    register_blueprint_once(flask_app, auth_core_bp, url_prefix="/api")
    register_blueprint_once(flask_app, auth_v2_bp, url_prefix="/api/v2")
    print(
        "[baupass] domain/auth: login, logout, bootstrap, me, 2fa, password-reset, emergency-2fa + v2",
        flush=True,
    )
