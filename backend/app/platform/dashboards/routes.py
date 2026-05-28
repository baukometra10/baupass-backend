"""Role dashboards API."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

dashboards_bp = Blueprint("platform_dashboards", __name__)


def register_dashboards_blueprint(flask_app) -> None:
    from backend.server import get_db, require_auth, require_roles

    @dashboards_bp.get("/dashboard/role")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def role_dashboard():
        from .role_views import build_role_dashboard

        user = g.current_user or {}
        role = str(user.get("role") or "company-admin")
        cid = str(user.get("company_id") or "").strip()
        if role == "superadmin":
            cid = str(request.args.get("company_id") or cid or "").strip() or None
        return jsonify(build_role_dashboard(get_db(), role=role, company_id=cid, user=user))

    if "platform_dashboards" not in flask_app.blueprints:
        flask_app.register_blueprint(dashboards_bp, url_prefix="/api")
