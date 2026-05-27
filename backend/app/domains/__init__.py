"""
BauPass bounded contexts (Clean Architecture domains).

Each package exposes a Flask blueprint via ``register_*_blueprint(app)``.
Routes delegate to services; services use repositories or legacy helpers
during the incremental migration away from backend/server.py.
"""
from __future__ import annotations

import logging

from flask import Flask

logger = logging.getLogger("baupass.domains")


def register_domain_blueprints(flask_app: Flask) -> None:
    """Register all domain blueprints that have been extracted from server.py."""
    modules = (
        ("auth", "backend.app.domains.auth.routes", "register_auth_blueprint"),
        ("workers", "backend.app.domains.workers.routes", "register_workers_blueprint"),
        ("access", "backend.app.domains.access.routes", "register_access_blueprint"),
        ("billing", "backend.app.domains.billing.routes", "register_billing_blueprint"),
        ("notifications", "backend.app.domains.notifications.routes", "register_notifications_blueprint"),
        ("admin", "backend.app.domains.admin.routes", "register_admin_blueprint"),
        ("onboarding", "backend.app.domains.onboarding.routes", "register_onboarding_blueprint"),
    )
    for name, module_path, fn_name in modules:
        try:
            mod = __import__(module_path, fromlist=[fn_name])
            getattr(mod, fn_name)(flask_app)
        except Exception as exc:
            logger.exception("Domain blueprint failed: %s", name)
            print(f"[baupass] WARNING: domain/{name} skipped: {exc}", flush=True)
