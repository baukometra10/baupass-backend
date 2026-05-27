"""Admin domain v2 — dashboard API for modern admin SPA."""
from __future__ import annotations

from flask import Blueprint, Flask, jsonify

from ..shared import company_id_from_user, forbidden_company
from .service import AdminService

admin_domain_bp = Blueprint("admin_domain", __name__)
_service = AdminService()


def register_admin_blueprint(flask_app: Flask) -> None:
    from backend.server import get_db, require_auth, require_roles, utc_now

    @admin_domain_bp.get("/admin/overview")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_admin_overview():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        today = utc_now().strftime("%Y-%m-%d")
        return jsonify(_service.overview(get_db(), cid, today))

    flask_app.register_blueprint(admin_domain_bp, url_prefix="/api/v2")
