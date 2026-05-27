"""CDN / edge caching headers for static assets."""
from __future__ import annotations

import os

from flask import Flask, request


def register_cdn_middleware(flask_app: Flask) -> None:
    max_age = int(os.getenv("BAUPASS_CDN_CACHE_SECONDS", "86400"))

    @flask_app.after_request
    def _cdn_headers(response):
        path = request.path or ""
        static_ext = (".js", ".css", ".png", ".svg", ".woff2", ".ico", ".webp", ".wasm")
        shell_pages = {
            "/emp-app.html",
            "/worker-install.html",
            "/join.html",
            "/design-tokens.css",
            "/worker-build.json",
        }
        if path.endswith(static_ext) or path in shell_pages:
            response.headers.setdefault("Cache-Control", f"public, max-age={max_age}")
            response.headers.setdefault("X-CDN-Edge", "baupass")
        if path in shell_pages:
            response.headers.setdefault("Vary", "Accept-Encoding")
        return response
