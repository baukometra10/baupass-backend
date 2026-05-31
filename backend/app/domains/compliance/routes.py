"""Compliance domain — overview, expiring docs, reports."""
from __future__ import annotations

from flask import Blueprint, Flask

compliance_core_bp = Blueprint("compliance_domain_core", __name__)


def _register_core_compliance_routes() -> None:
    from backend.server import (
        compliance_expiring_docs,
        compliance_overview,
        compliance_reports_get,
    )

    rules = (
        ("/compliance/overview", compliance_overview, ("GET",)),
        ("/compliance/expiring-docs", compliance_expiring_docs, ("GET",)),
        ("/compliance-reports", compliance_reports_get, ("GET",)),
    )
    for path, view_func, methods in rules:
        compliance_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))


def register_compliance_blueprint(flask_app: Flask) -> None:
    _register_core_compliance_routes()
    flask_app.register_blueprint(compliance_core_bp, url_prefix="/api")
    print("[baupass] domain/compliance: overview, expiring-docs, reports", flush=True)
