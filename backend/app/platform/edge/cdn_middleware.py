"""CDN / edge caching headers for static assets."""
from __future__ import annotations

import os

from flask import Flask, request


def register_cdn_middleware(flask_app: Flask) -> None:
    max_age = int(os.getenv("BAUPASS_CDN_CACHE_SECONDS", "86400"))
    no_store_shell = (
        "/emp-app.html",
        "/worker-install.html",
        "/join.html",
        "/worker-build.json",
        "/worker-sw.js",
        "/worker-app.js",
        "/worker.css",
        "/worker-layout-v2.css",
        "/worker-polish.css",
        "/worker-login.css",
        "/emp-app-manifest.json",
    )

    @flask_app.after_request
    def _cdn_headers(response):
        path = request.path or ""
        if path in no_store_shell or path.startswith("/worker-"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers.setdefault("X-CDN-Edge", "baupass-shell")
            return response
        static_ext = (".js", ".css", ".png", ".svg", ".woff2", ".ico", ".webp", ".wasm")
        shell_pages = {
            "/design-tokens.css",
        }
        if path.endswith(static_ext) or path in shell_pages:
            response.headers.setdefault("Cache-Control", f"public, max-age={max_age}")
            response.headers.setdefault("X-CDN-Edge", "baupass")
        if path in shell_pages:
            response.headers.setdefault("Vary", "Accept-Encoding")
        return response
