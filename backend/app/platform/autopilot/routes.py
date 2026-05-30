"""Autopilot settings API."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

autopilot_bp = Blueprint("platform_autopilot", __name__)


def register_autopilot_blueprint(flask_app) -> None:
    from backend.server import get_db, require_auth, require_roles

    def _company_id() -> str:
        user = g.current_user
        payload = request.get_json(silent=True) or {}
        if user.get("role") == "superadmin":
            return str(
                request.args.get("company_id")
                or payload.get("company_id")
                or payload.get("companyId")
                or ""
            ).strip()
        return str(user.get("company_id") or "").strip()

    @autopilot_bp.get("/platform/autopilot/settings")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def get_autopilot_settings():
        from .settings import DEFAULTS, get_settings

        cid = _company_id()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        settings = get_settings(get_db(), cid)
        return jsonify({"companyId": cid, "settings": settings, "defaults": DEFAULTS})

    @autopilot_bp.patch("/platform/autopilot/settings")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def patch_autopilot_settings():
        from .settings import save_settings

        cid = _company_id()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        body = request.get_json(silent=True) or {}
        patch = body.get("settings") if isinstance(body.get("settings"), dict) else body
        user = g.current_user
        saved = save_settings(
            get_db(),
            cid,
            patch,
            actor=str(user.get("id") or user.get("username") or ""),
        )
        return jsonify({"ok": True, "companyId": cid, "settings": saved})

    @autopilot_bp.post("/platform/autopilot/run")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def run_autopilot_now():
        from .runner import run_autopilot_cycle, run_company_autopilot

        cid = _company_id()
        db = get_db()
        user = g.current_user
        if cid:
            result = run_company_autopilot(db, cid)
        elif user.get("role") == "superadmin":
            result = run_autopilot_cycle(db)
        else:
            return jsonify({"error": "company_id_required"}), 400
        return jsonify(result)

    flask_app.register_blueprint(autopilot_bp, url_prefix="/api")
