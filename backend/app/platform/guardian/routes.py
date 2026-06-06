"""Platform Guardian API."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

guardian_bp = Blueprint("platform_guardian", __name__)


def register_guardian_blueprint(flask_app) -> None:
    from backend.server import require_auth, require_roles

    from .runner import get_guardian_snapshot, guardian_enabled, run_guardian_cycle

    @guardian_bp.get("/guardian/status")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def guardian_status():
        snapshot = get_guardian_snapshot()
        if not snapshot.get("timestamp"):
            host = (request.host or "").strip()
            public_url = request.url_root.rstrip("/")
            snapshot = run_guardian_cycle(current_app._get_current_object(), host=host, public_url=public_url)
        return jsonify(snapshot), 200

    @guardian_bp.post("/guardian/check")
    @require_auth
    @require_roles("superadmin")
    def guardian_check_now():
        host = (request.host or "").strip()
        public_url = request.url_root.rstrip("/")
        snapshot = run_guardian_cycle(
            current_app._get_current_object(),
            host=host,
            public_url=public_url,
            force_alert=True,
        )
        return jsonify(snapshot), 200

    flask_app.register_blueprint(guardian_bp, url_prefix="/api")
