"""
Optional OpenTelemetry distributed tracing.
Enable with OTEL_EXPORTER_OTLP_ENDPOINT or BAUPASS_OTEL=1.
"""
from __future__ import annotations

import logging
import os

from flask import Flask

logger = logging.getLogger("baupass.otel")


def init_tracing(flask_app: Flask) -> None:
    if os.getenv("BAUPASS_OTEL", "").strip() not in {"1", "true", "yes"}:
        if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip():
            return
    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        resource = Resource.create({"service.name": "baupass-api"})
        provider = TracerProvider(resource=resource)
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        else:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        FlaskInstrumentor().instrument_app(flask_app)

        @flask_app.after_request
        def _attach_trace_headers(response):
            # Helps correlate frontend/API logs even without full OTEL backend UI.
            current = trace.get_current_span()
            ctx = current.get_span_context() if current else None
            if ctx and getattr(ctx, "trace_id", 0):
                response.headers.setdefault("X-Trace-Id", f"{ctx.trace_id:032x}")
            return response

        logger.info("OpenTelemetry tracing enabled")
    except ImportError:
        logger.warning("opentelemetry packages not installed")
