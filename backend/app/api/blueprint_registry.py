"""
Register modular API blueprints on the legacy Flask app.
"""
from __future__ import annotations

from flask import Flask


def register_modular_blueprints(flask_app: Flask) -> None:
    from backend.app.api.worker_app_routes import register_worker_app_blueprint
    from backend.app.domains import register_domain_blueprints
    from backend.app.platform import register_platform_blueprints

    register_worker_app_blueprint(flask_app)
    register_domain_blueprints(flask_app)
    register_platform_blueprints(flask_app)
