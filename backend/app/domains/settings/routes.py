"""Settings domain — global SMTP/IMAP/OTP configuration."""
from __future__ import annotations

from flask import Blueprint, Flask

from .._routes import register_blueprint_once

settings_core_bp = Blueprint("settings_domain_core", __name__)


def _register_core_settings_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted, register_blueprint_once

    if routes_already_mounted("settings"):
        return
    from backend.server import (
        get_settings,
        list_imap_folders,
        otp_test_send,
        resend_test,
        smtp_diagnose,
        smtp_test,
        test_imap_connection,
        update_settings,
    )

    rules = (
        ("/settings", get_settings, ("GET",)),
        ("/settings", update_settings, ("PUT",)),
        ("/settings/smtp-test", smtp_test, ("POST",)),
        ("/settings/smtp-diagnose", smtp_diagnose, ("POST",)),
        ("/settings/resend-test", resend_test, ("POST",)),
        ("/settings/otp-test", otp_test_send, ("POST",)),
        ("/settings/imap/test", test_imap_connection, ("POST",)),
        ("/settings/imap/list-folders", list_imap_folders, ("POST",)),
    )
    for path, view_func, methods in rules:
        settings_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))
    mark_routes_mounted("settings")


def register_settings_blueprint(flask_app: Flask) -> None:
    _register_core_settings_routes()
    register_blueprint_once(flask_app, settings_core_bp, url_prefix="/api")
    print("[baupass] domain/settings: global config routes", flush=True)
