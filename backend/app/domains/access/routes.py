"""Access domain — gates, access logs (handlers in server until extracted)."""
from __future__ import annotations

from flask import Blueprint, Flask, jsonify

from ..shared import company_id_from_user, forbidden_company
from .service import AccessService

access_core_bp = Blueprint("access_domain_core", __name__)
access_v2_bp = Blueprint("access_domain_v2", __name__)
_service = AccessService()


def _register_core_access_routes() -> None:
    from backend.server import (
        access_day_close_check,
        access_summary,
        acknowledge_day_close,
        create_access_log,
        export_access_csv,
        gate_emergency_token_cache,
        gate_heartbeat,
        gate_ingest,
        gate_ops_metrics,
        gate_tap,
        gate_tap_batch,
        list_access_logs,
        list_latest_access_logs,
    )

    rules = (
        ("/access-logs", list_access_logs, ("GET",)),
        ("/access-logs/latest", list_latest_access_logs, ("GET",)),
        ("/access-logs/export.csv", export_access_csv, ("GET",)),
        ("/access-logs/summary", access_summary, ("GET",)),
        ("/access-logs/day-close-check", access_day_close_check, ("GET",)),
        ("/access-logs/day-close-ack", acknowledge_day_close, ("POST",)),
        ("/access-logs", create_access_log, ("POST",)),
        ("/gates/tap", gate_tap, ("POST",)),
        ("/gates/tap/batch", gate_tap_batch, ("POST",)),
        ("/gates/ops-metrics", gate_ops_metrics, ("GET",)),
        ("/gates/heartbeat", gate_heartbeat, ("POST",)),
        ("/gates/emergency-token-cache", gate_emergency_token_cache, ("GET",)),
        ("/gates/ingest", gate_ingest, ("POST",)),
    )
    for path, view_func, methods in rules:
        access_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))


def register_access_blueprint(flask_app: Flask) -> None:
    from backend.server import get_db, require_auth, require_roles

    _register_core_access_routes()

    @access_v2_bp.get("/access/live")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def v2_live_access():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        return jsonify(_service.live_access_feed(get_db(), cid))

    @access_v2_bp.get("/access/zones")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_access_zones():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        return jsonify(_service.geofence_zones(get_db(), cid))

    flask_app.register_blueprint(access_core_bp, url_prefix="/api")
    flask_app.register_blueprint(access_v2_bp, url_prefix="/api/v2")
    print(
        "[baupass] domain/access: access-logs*, gates/* + v2 live/zones",
        flush=True,
    )
