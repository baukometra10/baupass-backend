"""CDN / edge caching headers for static assets."""
from __future__ import annotations

import os

from flask import Flask, request


def register_cdn_middleware(flask_app: Flask) -> None:
    max_age = int(os.getenv("BAUPASS_CDN_CACHE_SECONDS", "86400"))

    @flask_app.after_request
    def _cdn_headers(response):
        path = request.path or ""
        if path.endswith((".js", ".css", ".png", ".svg", ".woff2", ".ico", ".webp")):
            response.headers.setdefault("Cache-Control", f"public, max-age={max_age}")
            response.headers.setdefault("X-CDN-Edge", "baupass")
        return response
