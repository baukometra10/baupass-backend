"""RBAC catalog API (read-only roadmap)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

rbac_bp = Blueprint("rbac_catalog", __name__)


def register_rbac_blueprint(flask_app) -> None:
    @rbac_bp.get("/platform/rbac/catalog")
    def rbac_catalog_route():
        from .catalog import rbac_catalog

        lang = (request.args.get("lang") or "de").strip().lower()[:2]
        return jsonify(rbac_catalog(lang))

    flask_app.register_blueprint(rbac_bp, url_prefix="/api")
