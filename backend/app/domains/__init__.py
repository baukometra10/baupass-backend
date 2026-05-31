"""
BauPass bounded contexts (Clean Architecture domains).

Each package exposes ``register_*_blueprint(app)``.
"""
from __future__ import annotations

import logging

from flask import Flask

logger = logging.getLogger("baupass.domains")


def register_domain_blueprints(flask_app: Flask) -> None:
    """Register domain blueprints (API routes migrated from server.py)."""
    modules = (
        ("auth", "backend.app.domains.auth.routes", "register_auth_blueprint"),
        ("settings", "backend.app.domains.settings.routes", "register_settings_blueprint"),
        ("companies", "backend.app.domains.companies.routes", "register_companies_blueprint"),
        ("workers", "backend.app.domains.workers.routes", "register_workers_blueprint"),
        ("access", "backend.app.domains.access.routes", "register_access_blueprint"),
        ("billing", "backend.app.domains.billing.routes", "register_billing_blueprint"),
        ("notifications", "backend.app.domains.notifications.routes", "register_notifications_blueprint"),
        ("admin", "backend.app.domains.admin.routes", "register_admin_blueprint"),
        ("onboarding", "backend.app.domains.onboarding.routes", "register_onboarding_blueprint"),
        ("reporting", "backend.app.domains.reporting.routes", "register_reporting_blueprint"),
    )
    results: list[tuple[str, str]] = []
    for name, module_path, fn_name in modules:
        try:
            mod = __import__(module_path, fromlist=[fn_name])
            getattr(mod, fn_name)(flask_app)
            results.append((name, "ok"))
        except Exception as exc:
            logger.exception("Domain blueprint failed: %s", name)
            print(f"[baupass] WARNING: domain/{name} skipped: {exc}", flush=True)
            results.append((name, f"error: {exc}"))

    failed = [name for name, status in results if status != "ok"]
    if failed:
        print(f"[baupass] Domains: {len(results) - len(failed)}/{len(results)} registered; failed: {failed}", flush=True)
    else:
        print(f"[baupass] Domains: all {len(results)} blueprints registered", flush=True)

    flask_app.extensions["domain_blueprints"] = results
