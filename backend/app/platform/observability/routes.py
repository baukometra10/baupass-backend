"""
Metrics and observability HTTP routes.
"""
from __future__ import annotations

from flask import Blueprint, Flask, Response, jsonify

from .metrics import metrics_content_type, metrics_payload

metrics_bp = Blueprint("platform_metrics", __name__)


@metrics_bp.get("/metrics")
def prometheus_metrics():
    """Prometheus scrape endpoint."""
    return Response(metrics_payload(), mimetype=metrics_content_type())


@metrics_bp.get("/observability/status")
def observability_status():
    import os

    return jsonify(
        {
            "prometheus": True,
            "sentry": bool(os.getenv("SENTRY_DSN", "").strip()),
            "structured_logs": os.getenv("BAUPASS_STRUCTURED_LOGS", "1") in {"1", "true", "yes"},
        }
    )


def register_metrics_blueprint(flask_app: Flask) -> None:
    flask_app.register_blueprint(metrics_bp)
