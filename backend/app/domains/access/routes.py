"""Access domain v2 routes."""
from __future__ import annotations

from flask import Blueprint, Flask, jsonify

from ..shared import company_id_from_user, forbidden_company
from .service import AccessService

access_domain_bp = Blueprint("access_domain", __name__)
_service = AccessService()


def register_access_blueprint(flask_app: Flask) -> None:
    from backend.server import require_auth, require_roles, get_db

    @access_domain_bp.get("/access/live")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def v2_live_access():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        return jsonify(_service.live_access_feed(get_db(), cid))

    @access_domain_bp.get("/access/zones")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_access_zones():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        return jsonify(_service.geofence_zones(get_db(), cid))

    flask_app.register_blueprint(access_domain_bp, url_prefix="/api/v2")
