"""
Metrics and observability HTTP routes.
"""
from __future__ import annotations

import os
import secrets

from flask import Blueprint, Flask, Response, jsonify, request

metrics_bp = Blueprint("platform_metrics", __name__)


def _metrics_authorized() -> bool:
    expected = (os.getenv("BAUPASS_METRICS_TOKEN") or "").strip()
    if not expected:
        return not bool((os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_GIT_COMMIT_SHA") or "").strip())
    supplied = (
        (request.headers.get("Authorization") or "").replace("Bearer ", "", 1).strip()
        or request.headers.get("X-Metrics-Token")
        or request.args.get("token")
        or ""
    ).strip()
    return bool(supplied) and secrets.compare_digest(supplied, expected)


@metrics_bp.get("/metrics")
def prometheus_metrics():
    if not _metrics_authorized():
        return jsonify({"error": "forbidden"}), 403
    try:
        from .metrics import metrics_content_type, metrics_payload

        return Response(metrics_payload(), mimetype=metrics_content_type())
    except ImportError:
        return Response("# prometheus_client not installed\n", mimetype="text/plain"), 503


def register_metrics_blueprint(flask_app: Flask) -> None:
    from backend.server import require_auth, require_roles

    @metrics_bp.get("/observability/status")
    @require_auth
    @require_roles("superadmin")
    def observability_status():
        modular = []
        try:
            from flask import current_app

            modular = current_app.extensions.get("modular_blueprints", [])
        except Exception:
            pass
        return jsonify(
            {
                "prometheus": True,
                "grafana": {"dashboards": "deploy/grafana/", "importRequired": True},
                "sentry": bool(os.getenv("SENTRY_DSN", "").strip()),
                "structured_logs": os.getenv("BAUPASS_STRUCTURED_LOGS", "1") in {"1", "true", "yes"},
                "log_forwarder": bool(os.getenv("BAUPASS_LOG_FORWARD_URL", "").strip()),
                "otel": os.getenv("BAUPASS_OTEL", "0") in {"1", "true", "yes"}
                or bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()),
                "platform_enabled": os.getenv("BAUPASS_PLATFORM_ENABLED", "1") not in {"0", "false", "no"},
                "modular_blueprints": modular,
            }
        )

    flask_app.register_blueprint(metrics_bp)
