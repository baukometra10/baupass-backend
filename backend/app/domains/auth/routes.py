"""Auth domain v2 — session layer on Clean Architecture."""
from __future__ import annotations

from flask import Blueprint, Flask, g, jsonify

from .service import AuthService

auth_domain_bp = Blueprint("auth_domain", __name__)
_service = AuthService()


def register_auth_blueprint(flask_app: Flask) -> None:
    from backend.server import require_auth, get_db

    @auth_domain_bp.get("/auth/session")
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

    @auth_domain_bp.post("/auth/revoke")
    @require_auth
    def v2_revoke():
        _service.logout(g.token, g.current_user)
        return jsonify({"ok": True})

    flask_app.register_blueprint(auth_domain_bp, url_prefix="/api/v2")
