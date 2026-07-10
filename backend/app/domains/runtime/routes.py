"""Runtime domain — health, system, public API, QR utilities."""
from __future__ import annotations

from flask import Blueprint, Flask

from .._routes import mount_rules_once, register_blueprint_once
from .qr_views import api_qr_hex, api_qr_png

runtime_core_bp = Blueprint("runtime_domain_core", __name__)


def _register_core_runtime_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted

    if routes_already_mounted("runtime"):
        return
    from backend.server import (
        api_health,
        api_health_dr,
        api_health_live,
        api_health_platform,
        api_health_queues,
        api_health_ready,
        demo_seed,
        get_review_form_info,
        list_reviews,
        phone_test_api,
        public_branding,
        public_tenant_branding,
        set_superadmin_preview_session,
        submit_review,
        system_clear_admin_ip_whitelist,
        system_recover_admin,
        system_repair,
        system_runtime_check,
        system_status,
    )

    mount_rules_once(
        "runtime_core",
        runtime_core_bp,
        (
            ("/health", api_health, ("GET",)),
            ("/health/live", api_health_live, ("GET",)),
            ("/health/platform", api_health_platform, ("GET",)),
            ("/health/ready", api_health_ready, ("GET",)),
            ("/health/queues", api_health_queues, ("GET",)),
            ("/health/dr", api_health_dr, ("GET",)),
            ("/system/status", system_status, ("GET",)),
            ("/system/runtime-check", system_runtime_check, ("GET",)),
            ("/system/recover-admin", system_recover_admin, ("POST",)),
            ("/system/clear-admin-ip-whitelist", system_clear_admin_ip_whitelist, ("POST",)),
            ("/system/repair", system_repair, ("POST",)),
            ("/superadmin/preview-session", set_superadmin_preview_session, ("POST",)),
            ("/public/branding", public_branding, ("GET",)),
            ("/public/tenant-branding", public_tenant_branding, ("GET",)),
            ("/public/review", get_review_form_info, ("GET",)),
            ("/public/review/submit", submit_review, ("POST",)),
            ("/phone-test", phone_test_api, ("GET",)),
            ("/demo-seed", demo_seed, ("POST",)),
            ("/reviews", list_reviews, ("GET",)),
            ("/qr.png", api_qr_png, ("GET",)),
            ("/qr", api_qr_hex, ("GET",)),
        ),
    )


def register_runtime_blueprint(flask_app: Flask) -> None:
    _register_core_runtime_routes()
    register_blueprint_once(flask_app, runtime_core_bp, url_prefix="/api")
    print("[baupass] domain/runtime: health, system, public, qr", flush=True)
