"""
HTTP metrics middleware for Prometheus (optional dependency).
"""
from __future__ import annotations

import logging
import time

from flask import Flask, g, request

logger = logging.getLogger("baupass.metrics")


def register_metrics_middleware(flask_app: Flask) -> None:
    try:
        from .metrics import HTTP_LATENCY, HTTP_REQUESTS
    except ImportError:
        logger.warning("prometheus_client not installed — /metrics disabled")
        return

    @flask_app.before_request
    def _metrics_start() -> None:
        g._metrics_start = time.monotonic()

    @flask_app.after_request
    def _metrics_record(response):
        start = getattr(g, "_metrics_start", None)
        if start is None:
            return response
        duration = time.monotonic() - start
        endpoint = str(request.url_rule.rule) if request.url_rule is not None else "unknown"
        method = request.method
        status = str(response.status_code)
        try:
            HTTP_REQUESTS.labels(method=method, endpoint=endpoint, status=status).inc()
            HTTP_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)
        except Exception:
            pass
        return response
