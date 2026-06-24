"""
WorkPass – Worker App API (Blueprint)
=====================================
Mitarbeiter-PWA routes migrated from server.py.
View logic stays in backend.server; this module mounts URLs on a blueprint.
"""
from __future__ import annotations

import sys

from flask import Blueprint

# (url_suffix, handler attribute on legacy server module, HTTP methods)
WORKER_APP_ROUTES: tuple[tuple[str, str, list[str]], ...] = (
    ("/login", "worker_app_login", ["POST"]),
    ("/proximity-login", "worker_app_proximity_login", ["POST"]),
    ("/me", "worker_app_me", ["GET"]),
    ("/team-snapshot", "worker_app_team_snapshot", ["GET"]),
    ("/offline-events", "worker_app_sync_offline_events", ["POST"]),
    ("/logout", "worker_app_logout", ["POST"]),
    ("/photo", "update_worker_photo", ["POST"]),
    ("/wallet/pass", "get_worker_wallet_pass", ["GET"]),
    ("/wallet/pass/file/<pass_object_id>.pkpass", "get_worker_wallet_pass_file", ["GET"]),
    ("/wallet/pass/google/<pass_object_id>", "get_worker_wallet_google_redirect", ["GET"]),
    ("/hce/device/register", "worker_app_hce_device_register", ["POST"]),
    ("/dynamic-qr", "worker_app_dynamic_qr", ["GET"]),
    ("/hce/bootstrap", "worker_app_hce_bootstrap", ["POST"]),
    ("/access-last", "worker_app_access_last", ["GET"]),
    ("/verify-pin", "worker_app_verify_pin", ["POST"]),
    ("/push-vapid-key", "get_vapid_public_key", ["GET"]),
    ("/push-subscribe", "worker_push_subscribe", ["POST"]),
    ("/leave-requests", "worker_get_leave_requests", ["GET"]),
    ("/leave-requests", "worker_submit_leave_request", ["POST"]),
    ("/leave-requests/<req_id>/send-email", "worker_send_leave_request_email", ["POST"]),
    ("/my-timesheets", "worker_app_my_timesheets", ["GET"]),
    ("/my-documents", "worker_app_my_documents", ["GET"]),
    ("/my-documents/<doc_id>/download", "worker_app_my_document_download", ["GET"]),
    ("/deployment-plan", "worker_app_deployment_plan", ["GET"]),
    ("/deployment-plan/pdf", "worker_app_deployment_plan_pdf", ["GET"]),
    ("/deployment-plan/day-response", "worker_app_deployment_plan_day_response", ["POST"]),
    ("/notifications", "notifications_get", ["GET"]),
    ("/notifications/<notif_id>/mark-read", "notifications_mark_read", ["POST"]),
    ("/company-admins", "worker_get_company_admins", ["GET"]),
    ("/site-presence", "worker_app_site_presence", ["POST"]),
    ("/site-leave", "worker_app_site_leave", ["POST"]),
    ("/attendance/nfc", "worker_app_attendance_nfc", ["POST"]),
    ("/push/register", "worker_app_push_register", ["POST"]),
    ("/push/status", "worker_app_push_status", ["GET"]),
    ("/usage/event", "worker_app_usage_event", ["POST"]),
)


def _resolve_legacy_server_module():
    """
    Return the loaded legacy server module without triggering a nested import.

    `python backend/server.py` loads the file as __main__; importing backend.server
    would execute server.py a second time and register blueprints on the wrong app.
    """
    for name in ("backend.server", "__main__", "server"):
        mod = sys.modules.get(name)
        handler = getattr(mod, "worker_app_login", None) if mod is not None else None
        if callable(handler):
            return mod
    raise RuntimeError("Legacy server module is not loaded yet (worker_app_login missing)")


def register_worker_app_blueprint(flask_app) -> None:
    """Mount worker-app handlers from the legacy server module."""
    if "worker_app" in flask_app.blueprints:
        return

    legacy = _resolve_legacy_server_module()
    worker_app_bp = Blueprint("worker_app", __name__)

    for path, handler_name, methods in WORKER_APP_ROUTES:
        view_func = getattr(legacy, handler_name, None)
        if view_func is None or not callable(view_func):
            raise RuntimeError(f"Legacy worker-app handler not found: {handler_name}")
        worker_app_bp.add_url_rule(path, handler_name, view_func, methods=methods)

    flask_app.register_blueprint(worker_app_bp, url_prefix="/api/worker-app")

    print(
        f"[baupass] Worker-app blueprint registered ({len(WORKER_APP_ROUTES)} routes)",
        flush=True,
    )
