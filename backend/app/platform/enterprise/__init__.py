"""Enterprise gap-fill modules — integrations, automation, heatmap, emergency, etc."""
from __future__ import annotations

from flask import Flask


def register_enterprise_blueprints(flask_app: Flask) -> None:
    from .routes import register_enterprise_routes

    register_enterprise_routes(flask_app)
