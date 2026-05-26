"""Notifications domain v2 routes."""
from __future__ import annotations

from flask import Blueprint, Flask, g

from .service import NotificationsService

notifications_domain_bp = Blueprint("notifications_domain", __name__)
_service = NotificationsService()


def register_notifications_blueprint(flask_app: Flask) -> None:
    from backend.server import require_auth, require_roles, get_db

    @notifications_domain_bp.get("/notifications/inbox")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_notifications_inbox():
        from ..shared import company_id_from_user, forbidden_company

        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        return _service.inbox(get_db(), cid)

    flask_app.register_blueprint(notifications_domain_bp, url_prefix="/api/v2")
