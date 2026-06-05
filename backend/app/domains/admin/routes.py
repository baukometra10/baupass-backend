"""Admin domain — legacy /api/admin/* + v2 dashboard."""
from __future__ import annotations

from flask import Blueprint, Flask, jsonify

from .._routes import register_blueprint_once
from ..shared import company_id_from_user, forbidden_company
from .service import AdminService

admin_core_bp = Blueprint("admin_domain_core", __name__)
admin_v2_bp = Blueprint("admin_domain_v2", __name__)
_service = AdminService()


def _register_core_admin_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted, register_blueprint_once

    if routes_already_mounted("admin"):
        return
    from backend.server import (
        admin_create_database_backup,
        admin_gate_devices,
        admin_list_database_backups,
        create_device,
        dead_letter_stats,
        delete_device,
        device_health_summary,
        export_device_event_dead_letters_csv,
        get_device_event_dead_letter,
        debug_imap_settings,
        export_audit_csv,
        export_payload,
        get_wallet_runtime_status,
        import_payload,
        list_audit_logs,
        list_device_event_dead_letters,
        list_devices,
        reprocess_device_event_dead_letter,
        resolve_device_event_dead_letter,
    )

    rules = (
        ("/export", export_payload, ("GET",)),
        ("/import", import_payload, ("POST",)),
        ("/debug/imap-settings", debug_imap_settings, ("GET",)),
        ("/audit-logs/export.csv", export_audit_csv, ("GET",)),
        ("/audit-logs", list_audit_logs, ("GET",)),
        ("/admin/wallet/runtime-status", get_wallet_runtime_status, ("GET",)),
        ("/admin/database/backup", admin_create_database_backup, ("POST",)),
        ("/admin/database/backups", admin_list_database_backups, ("GET",)),
        ("/admin/device-events/dead-letters/stats", dead_letter_stats, ("GET",)),
        ("/admin/device-events/dead-letters/export.csv", export_device_event_dead_letters_csv, ("GET",)),
        ("/admin/device-events/dead-letters", list_device_event_dead_letters, ("GET",)),
        (
            "/admin/device-events/dead-letters/<event_uid>/reprocess",
            reprocess_device_event_dead_letter,
            ("POST",),
        ),
        (
            "/admin/device-events/dead-letters/<event_uid>/resolve",
            resolve_device_event_dead_letter,
            ("POST",),
        ),
        ("/admin/device-events/dead-letters/<event_uid>", get_device_event_dead_letter, ("GET",)),
        ("/admin/devices/health-summary", device_health_summary, ("GET",)),
        ("/admin/devices", list_devices, ("GET",)),
        ("/admin/devices", create_device, ("POST",)),
        ("/admin/devices/<device_id>", delete_device, ("DELETE",)),
        ("/admin/gate-devices", admin_gate_devices, ("GET",)),
    )
    for path, view_func, methods in rules:
        admin_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))
    mark_routes_mounted("admin")


def register_admin_blueprint(flask_app: Flask) -> None:
    from backend.server import get_db, require_auth, require_roles, utc_now

    _register_core_admin_routes()

    @admin_v2_bp.get("/admin/overview")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_admin_overview():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        today = utc_now().strftime("%Y-%m-%d")
        return jsonify(_service.overview(get_db(), cid, today))

    register_blueprint_once(flask_app, admin_core_bp, url_prefix="/api")
    register_blueprint_once(flask_app, admin_v2_bp, url_prefix="/api/v2")
    print("[baupass] domain/admin: all /api/admin/* routes on admin_core_bp", flush=True)
