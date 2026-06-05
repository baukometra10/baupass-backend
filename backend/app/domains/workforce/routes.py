"""Workforce domain — foreman, analytics, sync (shift routes via shift_api blueprint)."""
from __future__ import annotations

from flask import Blueprint, Flask

from .._routes import register_blueprint_once

workforce_core_bp = Blueprint("workforce_domain_core", __name__)


def _register_core_workforce_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted, register_blueprint_once

    if routes_already_mounted("workforce"):
        return
    from backend.server import (
        analytics_document_health,
        analytics_export_csv,
        analytics_export_summary,
        analytics_punctuality_report,
        analytics_worker_trends,
        foreman_crew_health,
        foreman_recent_notifications,
        foreman_send_alert,
        foreman_team_status,
        foreman_tomorrow_forecast,
        sync_get_conflicts,
        sync_resolve_conflict,
    )

    rules = (
        ("/foreman/team-status", foreman_team_status, ("GET",)),
        ("/foreman/crew-health", foreman_crew_health, ("GET",)),
        ("/foreman/tomorrow-forecast", foreman_tomorrow_forecast, ("GET",)),
        ("/foreman/send-alert", foreman_send_alert, ("POST",)),
        ("/foreman/recent-notifications", foreman_recent_notifications, ("GET",)),
        ("/analytics/worker-trends", analytics_worker_trends, ("GET",)),
        ("/analytics/document-health", analytics_document_health, ("GET",)),
        ("/analytics/punctuality-report", analytics_punctuality_report, ("GET",)),
        ("/analytics/export/csv", analytics_export_csv, ("GET",)),
        ("/analytics/export/summary", analytics_export_summary, ("GET",)),
        ("/sync/conflicts", sync_get_conflicts, ("GET",)),
        ("/sync/resolve/<conflict_id>", sync_resolve_conflict, ("POST",)),
    )
    for path, view_func, methods in rules:
        workforce_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))
    mark_routes_mounted("workforce")


def register_workforce_blueprint(flask_app: Flask) -> None:
    _register_core_workforce_routes()
    register_blueprint_once(flask_app, workforce_core_bp, url_prefix="/api")
    print("[baupass] domain/workforce: foreman, analytics, sync", flush=True)
