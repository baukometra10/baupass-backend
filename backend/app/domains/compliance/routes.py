"""Compliance domain — overview, expiring docs, reports."""
from __future__ import annotations

from flask import Blueprint, Flask

from .._routes import register_blueprint_once

compliance_core_bp = Blueprint("compliance_domain_core", __name__)


def _register_core_compliance_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted, register_blueprint_once

    if routes_already_mounted("compliance"):
        return
    from backend.server import (
        compliance_expiring_docs,
        compliance_overview,
        compliance_reports_get,
        admin_gdpr_requests_list,
        admin_gdpr_request_resolve,
    )

    rules = (
        ("/compliance/overview", compliance_overview, ("GET",)),
        ("/compliance/expiring-docs", compliance_expiring_docs, ("GET",)),
        ("/compliance-reports", compliance_reports_get, ("GET",)),
        ("/gdpr-requests", admin_gdpr_requests_list, ("GET",)),
        ("/gdpr-requests/<request_id>/resolve", admin_gdpr_request_resolve, ("POST",)),
    )
    for path, view_func, methods in rules:
        compliance_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))
    mark_routes_mounted("compliance")


def register_compliance_blueprint(flask_app: Flask) -> None:
    _register_core_compliance_routes()
    register_blueprint_once(flask_app, compliance_core_bp, url_prefix="/api")
    print("[baupass] domain/compliance: overview, expiring-docs, reports", flush=True)
