"""Bootstrap helpers for legacy server.py route registration."""

from backend.app.health.route_probe import CRITICAL_API_ROUTES, build_api_route_probe, summarize_blueprint_status

__all__ = [
    "CRITICAL_API_ROUTES",
    "build_api_route_probe",
    "summarize_blueprint_status",
]
