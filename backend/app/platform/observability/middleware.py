"""
HTTP metrics middleware for Prometheus.
"""
from __future__ import annotations

import time

from flask import Flask, g, request

from .metrics import HTTP_LATENCY, HTTP_REQUESTS


def _endpoint_label() -> str:
    if request.url_rule is not None:
        return str(request.url_rule.rule)
    return "unknown"


def register_metrics_middleware(flask_app: Flask) -> None:
    @flask_app.before_request
    def _metrics_start() -> None:
        g._metrics_start = time.monotonic()

    @flask_app.after_request
    def _metrics_record(response):
        start = getattr(g, "_metrics_start", None)
        if start is None:
            return response
        duration = time.monotonic() - start
        method = request.method
        endpoint = _endpoint_label()
        status = str(response.status_code)
        HTTP_REQUESTS.labels(method=method, endpoint=endpoint, status=status).inc()
        HTTP_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)
        return response
