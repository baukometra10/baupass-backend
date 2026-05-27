"""
Workers domain — Clean Architecture API (v2, no conflict with legacy /api/workers).
"""
from __future__ import annotations

from flask import Blueprint, Flask, jsonify, request

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

    @workers_domain_bp.patch("/workers/<worker_id>/physical-card")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_assign_physical_card(worker_id):
        from backend.server import (
            ensure_unique_physical_card_id_or_raise,
            normalize_physical_card_id,
        )

        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        payload = request.get_json(silent=True) or {}
        physical_card_id = normalize_physical_card_id(payload.get("physicalCardId"))
        try:
            ensure_unique_physical_card_id_or_raise(
                get_db(), physical_card_id, worker_id_to_exclude=worker_id
            )
        except ValueError:
            return jsonify(
                {
                    "error": "duplicate_physical_card_id",
                    "message": "This NFC card is already assigned to another worker.",
                }
            ), 409
        updated = _service.assign_physical_card(get_db(), cid, worker_id, physical_card_id)
        if not updated:
            return jsonify({"error": "worker_not_found"}), 404
        get_db().commit()
        return jsonify({"ok": True, "workerId": worker_id, "physicalCardId": physical_card_id})

    @workers_domain_bp.get("/mobile/distribution")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_mobile_distribution():
        from backend.server import get_public_base_url
        from .mobile_distribution import build_mobile_distribution

        return jsonify(build_mobile_distribution(get_public_base_url()))

    flask_app.register_blueprint(workers_domain_bp, url_prefix="/api/v2")
