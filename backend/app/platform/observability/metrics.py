"""
Prometheus metrics for WorkPass.
"""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "baupass_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
HTTP_LATENCY = Histogram(
    "baupass_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
EVENTS_PUBLISHED = Counter(
    "baupass_events_published_total",
    "Domain events published",
    ["event_type"],
)
WEBHOOK_DELIVERIES = Counter(
    "baupass_webhook_deliveries_total",
    "Webhook delivery attempts",
    ["status"],
)


def metrics_payload() -> bytes:
    return generate_latest()


def metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST
