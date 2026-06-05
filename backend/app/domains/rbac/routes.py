"""RBAC domain — legacy roles API + company audit trail."""
from __future__ import annotations

from flask import Blueprint, Flask

from .._routes import register_blueprint_once

rbac_core_bp = Blueprint("rbac_domain_core", __name__)


def _register_core_rbac_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted, register_blueprint_once

    if routes_already_mounted("rbac"):
        return
    from backend.server import (
        audit_trail_get,
        role_assignments_create,
        roles_create,
        roles_get,
    )

    rules = (
        ("/audit-trail", audit_trail_get, ("GET",)),
        ("/roles", roles_get, ("GET",)),
        ("/roles", roles_create, ("POST",)),
        ("/role-assignments", role_assignments_create, ("POST",)),
    )
    for path, view_func, methods in rules:
        rbac_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))
    mark_routes_mounted("rbac")


def register_rbac_domain_blueprint(flask_app: Flask) -> None:
    _register_core_rbac_routes()
    register_blueprint_once(flask_app, rbac_core_bp, url_prefix="/api")
    print("[baupass] domain/rbac: roles, role-assignments, audit-trail", flush=True)
