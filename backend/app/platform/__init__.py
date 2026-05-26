"""
BauPass enterprise platform layer.

Observability, event bus, real-time SSE, public API (keys/webhooks), object storage.
"""
from __future__ import annotations

from flask import Flask


def init_platform(flask_app: Flask) -> None:
    """Initialize cross-cutting platform services on the legacy Flask app."""
    from .observability.sentry_init import init_sentry
    from .observability.middleware import register_metrics_middleware
    from .observability.tracing import init_tracing
    from .observability.log_forwarder import attach_log_forwarder
    from .security.zero_trust import register_zero_trust_middleware
    from .edge.cdn_middleware import register_cdn_middleware

    init_sentry(flask_app)
    register_metrics_middleware(flask_app)
    init_tracing(flask_app)
    attach_log_forwarder()
    register_zero_trust_middleware(flask_app)
    register_cdn_middleware(flask_app)


def register_platform_blueprints(flask_app: Flask) -> None:
    """Register all platform HTTP blueprints."""
    from .observability.routes import register_metrics_blueprint
    from .realtime.routes import register_realtime_blueprint
    from .realtime.websocket import init_socketio
    from .api_platform.routes import register_api_platform_blueprints
    from .ai.routes import register_ai_blueprint
    from .enterprise import register_enterprise_blueprints

    init_platform(flask_app)
    init_socketio(flask_app)
    register_metrics_blueprint(flask_app)
    register_realtime_blueprint(flask_app)
    register_api_platform_blueprints(flask_app)
    register_ai_blueprint(flask_app)
    register_enterprise_blueprints(flask_app)
