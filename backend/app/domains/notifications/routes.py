"""Notifications domain — worker notifications, system alerts, push triggers + v2."""
from __future__ import annotations

from flask import Blueprint, Flask

from .service import NotificationsService

notifications_core_bp = Blueprint("notifications_domain_core", __name__)
notifications_v2_bp = Blueprint("notifications_domain_v2", __name__)
_service = NotificationsService()


def _register_core_notification_routes() -> None:
    from backend.server import (
        list_system_alerts,
        notifications_delete,
        notifications_get,
        notifications_mark_read,
        trigger_checkout_reminders,
    )

    rules = (
        ("/notifications", notifications_get, ("GET",)),
        ("/notifications/<notif_id>/mark-read", notifications_mark_read, ("POST",)),
        ("/notifications/<notif_id>", notifications_delete, ("DELETE",)),
        ("/system-alerts", list_system_alerts, ("GET",)),
        ("/push/trigger-checkout-reminders", trigger_checkout_reminders, ("POST",)),
    )
    for path, view_func, methods in rules:
        notifications_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))


def register_notifications_blueprint(flask_app: Flask) -> None:
    from backend.server import get_db, require_auth, require_roles

    _register_core_notification_routes()

    @notifications_v2_bp.get("/notifications/inbox")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_notifications_inbox():
        from ..shared import company_id_from_user, forbidden_company

        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        return _service.inbox(get_db(), cid)

    flask_app.register_blueprint(notifications_core_bp, url_prefix="/api")
    flask_app.register_blueprint(notifications_v2_bp, url_prefix="/api/v2")
    print("[baupass] domain/notifications: core + v2 routes registered", flush=True)
