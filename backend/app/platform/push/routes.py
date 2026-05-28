"""Push platform status API."""
from __future__ import annotations

from flask import Blueprint, jsonify

push_bp = Blueprint("platform_push", __name__)


def register_push_blueprint(flask_app) -> None:
    from backend.server import get_db, require_auth, require_roles

    @push_bp.get("/platform/push/status")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def push_status():
        from .delivery import push_platform_status

        status = push_platform_status()
        db = get_db()
        try:
            row = db.execute(
                """
                SELECT COUNT(DISTINCT worker_id) AS workers,
                       COUNT(*) AS devices
                FROM worker_bound_devices
                WHERE status = 'active' AND push_token IS NOT NULL AND push_token != ''
                """
            ).fetchone()
            status["registeredDevices"] = int((row["devices"] if row else 0) or 0)
            status["workersWithPush"] = int((row["workers"] if row else 0) or 0)
        except Exception:
            status["registeredDevices"] = 0
            status["workersWithPush"] = 0
        try:
            row2 = db.execute("SELECT COUNT(*) AS c FROM push_subscriptions").fetchone()
            status["webPushSubscriptions"] = int((row2["c"] if row2 else 0) or 0)
        except Exception:
            status["webPushSubscriptions"] = 0
        return jsonify(status)

    if "platform_push" not in flask_app.blueprints:
        flask_app.register_blueprint(push_bp, url_prefix="/api")
