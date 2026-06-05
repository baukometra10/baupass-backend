"""Devices domain — registration, heartbeat, scan, signatures.

Note: ``/api/worker-app/*`` (except public mobile-setup) lives on ``worker_app`` blueprint.
"""
from __future__ import annotations

from flask import Blueprint, Flask

from .._routes import register_blueprint_once

devices_core_bp = Blueprint("devices_domain_core", __name__)


def _register_core_device_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted, register_blueprint_once

    if routes_already_mounted("devices"):
        return
    from backend.server import (
        device_biometric_auth,
        device_heartbeat,
        device_register,
        device_signature_capture,
        unified_scan,
        worker_app_mobile_setup_public,
    )

    rules = (
        ("/device/register", device_register, ("POST",)),
        ("/device/biometric-auth", device_biometric_auth, ("POST",)),
        ("/device/signature/capture", device_signature_capture, ("POST",)),
        ("/device/heartbeat", device_heartbeat, ("POST",)),
        ("/scan", unified_scan, ("POST",)),
        ("/worker-app/mobile-setup", worker_app_mobile_setup_public, ("GET",)),
    )
    for path, view_func, methods in rules:
        devices_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))
    mark_routes_mounted("devices")


def register_devices_blueprint(flask_app: Flask) -> None:
    _register_core_device_routes()
    register_blueprint_once(flask_app, devices_core_bp, url_prefix="/api")
    print("[baupass] domain/devices: register, heartbeat, scan, worker-app hooks", flush=True)
