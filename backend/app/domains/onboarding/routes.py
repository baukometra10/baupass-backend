"""Onboarding workflow API (v2)."""
from __future__ import annotations

from flask import Blueprint, Flask, jsonify, request

from .service import OnboardingService

onboarding_bp = Blueprint("onboarding_domain", __name__)
_service = OnboardingService()


def register_onboarding_blueprint(flask_app: Flask) -> None:
    from backend.server import require_auth, require_roles, get_db

    def _company_id() -> int:
        from flask import g

        return int(g.current_user.get("company_id") or 0)

    @onboarding_bp.post("/onboarding/start")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def start_onboarding():
        from flask import g

        cid = _company_id()
        if g.current_user.get("role") != "superadmin":
            cid = int(g.current_user.get("company_id") or 0)
        data = request.get_json(silent=True) or {}
        result = _service.start(get_db(), cid, data)
        code = 201 if result.get("ok") else 400
        return jsonify(result), code

    @onboarding_bp.post("/onboarding/<workflow_id>/advance")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def advance_onboarding(workflow_id: str):
        from flask import g

        cid = int(g.current_user.get("company_id") or 0)
        step = (request.get_json(silent=True) or {}).get("step", "").strip()
        result = _service.advance(get_db(), cid, workflow_id, step)
        return jsonify(result), (200 if result.get("ok") else 400)

    @onboarding_bp.get("/onboarding/active")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def list_onboarding():
        from flask import g

        cid = int(g.current_user.get("company_id") or 0)
        return jsonify({"workflows": _service.list_active(get_db(), cid)})

    flask_app.register_blueprint(onboarding_bp, url_prefix="/api/v2")
