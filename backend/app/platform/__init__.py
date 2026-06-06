"""
BauPass enterprise platform layer (optional modules — failures are non-fatal).
"""
from __future__ import annotations

import logging
import os
import traceback

from flask import Flask

logger = logging.getLogger("baupass.platform")


def _step(name: str, fn) -> None:
    try:
        fn()
    except Exception as exc:
        logger.warning("Platform step skipped (%s): %s", name, exc)
        print(f"[baupass] WARNING: platform/{name} skipped: {exc}", flush=True)
        traceback.print_exc()


def init_platform(flask_app: Flask) -> None:
    if os.getenv("BAUPASS_PLATFORM_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        print("[baupass] Platform layer disabled (BAUPASS_PLATFORM_ENABLED=0)", flush=True)
        return

    _step("sentry", lambda: __import__("backend.app.platform.observability.sentry_init", fromlist=["init_sentry"]).init_sentry(flask_app))
    _step("metrics", lambda: __import__("backend.app.platform.observability.middleware", fromlist=["register_metrics_middleware"]).register_metrics_middleware(flask_app))
    _step("tracing", lambda: __import__("backend.app.platform.observability.tracing", fromlist=["init_tracing"]).init_tracing(flask_app))
    _step("log_forwarder", lambda: __import__("backend.app.platform.observability.log_forwarder", fromlist=["attach_log_forwarder"]).attach_log_forwarder())
    _step("zero_trust", lambda: __import__("backend.app.platform.security.zero_trust", fromlist=["register_zero_trust_middleware"]).register_zero_trust_middleware(flask_app))
    _step("cdn", lambda: __import__("backend.app.platform.edge.cdn_middleware", fromlist=["register_cdn_middleware"]).register_cdn_middleware(flask_app))
    _step(
        "data_residency",
        lambda: __import__(
            "backend.app.platform.multi_region.middleware",
            fromlist=["register_data_residency_middleware"],
        ).register_data_residency_middleware(flask_app),
    )


def register_platform_blueprints(flask_app: Flask) -> None:
    if os.getenv("BAUPASS_PLATFORM_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return

    init_platform(flask_app)

    _step("socketio", lambda: __import__("backend.app.platform.realtime.websocket", fromlist=["init_socketio"]).init_socketio(flask_app))
    _step("metrics_routes", lambda: __import__("backend.app.platform.observability.routes", fromlist=["register_metrics_blueprint"]).register_metrics_blueprint(flask_app))
    _step("realtime", lambda: __import__("backend.app.platform.realtime.routes", fromlist=["register_realtime_blueprint"]).register_realtime_blueprint(flask_app))
    _step("api_platform", lambda: __import__("backend.app.platform.api_platform.routes", fromlist=["register_api_platform_blueprints"]).register_api_platform_blueprints(flask_app))
    _step("ai", lambda: __import__("backend.app.platform.ai.routes", fromlist=["register_ai_blueprint"]).register_ai_blueprint(flask_app))
    _step("enterprise", lambda: __import__("backend.app.platform.enterprise", fromlist=["register_enterprise_blueprints"]).register_enterprise_blueprints(flask_app))
    _step(
        "enterprise_layers",
        lambda: __import__(
            "backend.app.platform.enterprise_layers",
            fromlist=["register_enterprise_layers"],
        ).register_enterprise_layers(flask_app),
    )
    _step(
        "physical_operations",
        lambda: __import__(
            "backend.app.platform.physical_operations",
            fromlist=["register_physical_operations"],
        ).register_physical_operations(flask_app),
    )
    _step("inbox", lambda: __import__("backend.app.platform.inbox", fromlist=["register_inbox_blueprint"]).register_inbox_blueprint(flask_app))
    _step(
        "dashboards",
        lambda: __import__(
            "backend.app.platform.dashboards",
            fromlist=["register_dashboards_blueprint"],
        ).register_dashboards_blueprint(flask_app),
    )
    _step(
        "push",
        lambda: __import__(
            "backend.app.platform.push.routes",
            fromlist=["register_push_blueprint"],
        ).register_push_blueprint(flask_app),
    )
    _step(
        "entra_sso",
        lambda: __import__(
            "backend.app.platform.auth.entra_oidc",
            fromlist=["register_entra_auth_routes"],
        ).register_entra_auth_routes(flask_app),
    )
    _step(
        "google_sso",
        lambda: __import__(
            "backend.app.platform.auth.google_oidc",
            fromlist=["register_google_auth_routes"],
        ).register_google_auth_routes(flask_app),
    )
    _step(
        "keycloak_sso",
        lambda: __import__(
            "backend.app.platform.auth.keycloak_oidc",
            fromlist=["register_keycloak_auth_routes"],
        ).register_keycloak_auth_routes(flask_app),
    )
    _step(
        "saml_sso",
        lambda: __import__(
            "backend.app.platform.auth.saml_sp",
            fromlist=["register_saml_auth_routes"],
        ).register_saml_auth_routes(flask_app),
    )
    _step(
        "sso_catalog",
        lambda: __import__(
            "backend.app.platform.auth.sso_catalog",
            fromlist=["register_sso_catalog_routes"],
        ).register_sso_catalog_routes(flask_app),
    )
    _step(
        "sector",
        lambda: __import__(
            "backend.app.platform.sector.routes",
            fromlist=["register_sector_blueprint"],
        ).register_sector_blueprint(flask_app),
    )
    _step(
        "rbac_catalog",
        lambda: __import__(
            "backend.app.platform.rbac.routes",
            fromlist=["register_rbac_blueprint"],
        ).register_rbac_blueprint(flask_app),
    )
    _step(
        "rbac_assignments",
        lambda: __import__(
            "backend.app.platform.rbac.assignment_routes",
            fromlist=["register_rbac_assignment_blueprint"],
        ).register_rbac_assignment_blueprint(flask_app),
    )
    _step(
        "governance",
        lambda: __import__(
            "backend.app.platform.governance.routes",
            fromlist=["register_governance_blueprint"],
        ).register_governance_blueprint(flask_app),
    )
    _step(
        "autopilot",
        lambda: __import__(
            "backend.app.platform.autopilot",
            fromlist=["register_autopilot_blueprint"],
        ).register_autopilot_blueprint(flask_app),
    )
    _step(
        "guardian",
        lambda: __import__(
            "backend.app.platform.guardian",
            fromlist=["register_guardian_blueprint"],
        ).register_guardian_blueprint(flask_app),
    )
    _step(
        "workforce",
        lambda: __import__(
            "backend.app.platform.workforce",
            fromlist=["register_workforce_blueprint"],
        ).register_workforce_blueprint(flask_app),
    )
