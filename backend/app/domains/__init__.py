"""
BauPass bounded contexts (Clean Architecture domains).

Each package exposes a Flask blueprint via ``register_*_blueprint(app)``.
Routes delegate to services; services use repositories or legacy helpers
during the incremental migration away from backend/server.py.
"""
from __future__ import annotations

from flask import Flask


def register_domain_blueprints(flask_app: Flask) -> None:
    """Register all domain blueprints that have been extracted from server.py."""
    from .auth.routes import register_auth_blueprint
    from .workers.routes import register_workers_blueprint
    from .access.routes import register_access_blueprint
    from .billing.routes import register_billing_blueprint
    from .notifications.routes import register_notifications_blueprint

    register_auth_blueprint(flask_app)
    register_workers_blueprint(flask_app)
    register_access_blueprint(flask_app)
    register_billing_blueprint(flask_app)
    register_notifications_blueprint(flask_app)
