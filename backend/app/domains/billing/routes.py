"""Billing domain v2 routes."""
from __future__ import annotations

from flask import Blueprint, Flask

from ..shared import company_id_from_user, forbidden_company
from .service import BillingService

billing_domain_bp = Blueprint("billing_domain", __name__)
_service = BillingService()


def register_billing_blueprint(flask_app: Flask) -> None:
    from backend.server import require_auth, require_roles, get_db

    @billing_domain_bp.get("/billing/overview")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_billing_overview():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        return _service.subscription_overview(get_db(), cid)

    flask_app.register_blueprint(billing_domain_bp, url_prefix="/api/v2")
