"""
Global edge middleware — caching, API no-store, request correlation.

Runs even when BAUPASS_PLATFORM_ENABLED=0 so every deployment benefits.
"""
from __future__ import annotations

import os
import secrets
import time

from flask import Flask, g, request


def register_global_edge_middleware(flask_app: Flask) -> None:
    static_max_age = int(os.getenv("BAUPASS_CDN_CACHE_SECONDS", "86400"))
    pwa_shell_max_age = int(os.getenv("BAUPASS_PWA_SHELL_CACHE_SECONDS", "300"))
    api_cache = os.getenv("BAUPASS_API_CACHE_CONTROL", "no-store, no-cache, must-revalidate")

    @flask_app.before_request
    def _edge_request_start() -> None:
        g._edge_start = time.monotonic()
        if not request.headers.get("X-Request-Id"):
            g.request_id = secrets.token_hex(8)
        else:
            g.request_id = request.headers.get("X-Request-Id", "")[:64]

    @flask_app.after_request
    def _edge_response_headers(response):
        rid = getattr(g, "request_id", None)
        if rid:
            response.headers.setdefault("X-Request-Id", rid)

        path = request.path or ""
        if path.startswith("/api/") or path.startswith("/api/v"):
            response.headers["Cache-Control"] = api_cache
            response.headers.setdefault("Vary", "Authorization, Accept-Language")
        elif path in {"/emp-app.html", "/index.html", "/worker-build.json"}:
            response.headers.setdefault(
                "Cache-Control",
                f"public, max-age={pwa_shell_max_age}, must-revalidate",
            )
        elif path.endswith(
            (".js", ".css", ".png", ".svg", ".woff2", ".ico", ".webp", ".wasm", ".json")
        ) and not path.startswith("/api"):
            response.headers.setdefault("Cache-Control", f"public, max-age={static_max_age}")
            response.headers.setdefault("X-CDN-Edge", "baupass-static")

        start = getattr(g, "_edge_start", None)
        if start is not None:
            ms = int((time.monotonic() - start) * 1000)
            response.headers.setdefault("X-Response-Time-Ms", str(ms))

        return response
