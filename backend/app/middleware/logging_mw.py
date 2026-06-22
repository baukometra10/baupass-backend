"""
WorkPass – Structured Logging Middleware
=========================================
يُضيف:
  1. Request/Response logging منظَّم (JSON)
  2. Request-ID tracking عبر جميع الطبقات
  3. Performance monitoring (response time)
  4. Error tracking
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from flask import Flask, Response, g, request

logger = logging.getLogger("baupass.api")


def register_logging_middleware(app: Flask) -> None:
    """يُسجّل logging middleware على Flask app."""

    @app.before_request
    def _before():
        g.request_start = time.monotonic()
        g.request_id = (
            request.headers.get("X-Request-Id")
            or str(uuid.uuid4())
        )

    @app.after_request
    def _after(response: Response) -> Response:
        duration_ms = int((time.monotonic() - getattr(g, "request_start", time.monotonic())) * 1000)
        request_id = getattr(g, "request_id", "-")

        response.headers["X-Request-Id"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        # لا نُسجّل health checks أو static files
        path = request.path
        if path.startswith("/api/health") or path in {"/favicon.ico"} or path.startswith("/static/"):
            return response

        log_data: dict[str, Any] = {
            "request_id": request_id,
            "method": request.method,
            "path": path[:200],
            "query": (request.query_string.decode(errors="ignore") if request.query_string else "")[:300],
            "status": response.status_code,
            "duration_ms": duration_ms,
            "ip": _get_ip(),
            "user_agent": (request.headers.get("User-Agent") or "")[:200],
            "content_length": int(request.content_length or 0),
            "trace_id": (response.headers.get("X-Trace-Id") or "")[:64],
        }

        # معلومات المستخدم إذا متاحة
        user = getattr(g, "current_user", None)
        if user:
            log_data["user_id"] = user.get("id", "-")
            log_data["company_id"] = user.get("company_id", "-")
            log_data["role"] = user.get("role", "-")
        else:
            # fallback when endpoint is unauthenticated but scoped by header
            company_hint = (request.headers.get("X-Company-Id") or "").strip()
            if company_hint:
                log_data["company_id"] = company_hint[:64]

        # تسجيل بمستوى مناسب
        if response.status_code >= 500:
            logger.error("request", extra={"json_fields": log_data})
        elif response.status_code >= 400:
            logger.warning("request", extra={"json_fields": log_data})
        else:
            logger.info("request", extra={"json_fields": log_data})

        return response

    @app.errorhandler(Exception)
    def _unhandled_error(exc: Exception) -> tuple:
        logger.exception(
            "Unhandled exception: %s",
            exc,
            extra={"json_fields": {
                "request_id": getattr(g, "request_id", "-"),
                "path": request.path,
                "method": request.method,
            }},
        )
        from flask import jsonify
        return jsonify({"error": "internal_server_error", "message": "An unexpected error occurred."}), 500


def _get_ip() -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
    return forwarded.split(",", 1)[0].strip() if forwarded else (request.remote_addr or "unknown")
