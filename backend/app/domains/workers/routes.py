"""
Workers domain — Clean Architecture API (v2, no conflict with legacy /api/workers).
"""
from __future__ import annotations

from flask import Blueprint, Flask, g, jsonify

from ..shared import company_id_from_user, forbidden_company
from .service import WorkersService

workers_domain_bp = Blueprint("workers_domain", __name__)
_service = WorkersService()


def register_workers_blueprint(flask_app: Flask) -> None:
    from backend.server import require_auth, require_roles, get_db, utc_now

    @workers_domain_bp.get("/workers")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def v2_list_workers():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        return jsonify({"workers": _service.list_workers(get_db(), cid)})

    @workers_domain_bp.get("/workforce/tracking")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_workforce_tracking():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        today = utc_now().strftime("%Y-%m-%d")
        return jsonify(_service.workforce_tracking(get_db(), cid, today))

    flask_app.register_blueprint(workers_domain_bp, url_prefix="/api/v2")
