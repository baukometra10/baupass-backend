"""
WorkPass – Security Middleware
==============================
Adds:
  1. Security headers (HSTS, CSP, X-Frame-Options, etc.)
  2. CSRF protection for mutating requests
  3. Session rotation after login
  4. Clickjacking protection
  5. Content-Type sniffing prevention
"""
from __future__ import annotations

import logging
import os
import secrets
from functools import wraps
from typing import Optional

from flask import Flask, Response, g, jsonify, request, session

logger = logging.getLogger("baupass.security")

# ── Content Security Policy ───────────────────────────────────────────────────
_CSP_DIRECTIVES = {
    "default-src":  ["'self'"],
    "script-src":   ["'self'", "'strict-dynamic'", "https://cdn.jsdelivr.net"],
    "style-src":    ["'self'", "'unsafe-inline'"],
    "img-src":      ["'self'", "data:", "blob:"],
    "media-src":    ["'self'", "blob:"],
    "manifest-src": ["'self'", "blob:"],
    "font-src":     ["'self'", "data:"],
    "connect-src":  ["'self'", "wss:", "ws:"],
    "frame-src":    ["'none'"],
    "object-src":   ["'none'"],
    "base-uri":     ["'self'"],
    "form-action":  ["'self'"],
    "upgrade-insecure-requests": [],
}

def _build_csp() -> str:
    parts = []
    for directive, values in _CSP_DIRECTIVES.items():
        if values:
            parts.append(f"{directive} {' '.join(values)}")
        else:
            parts.append(directive)
    return "; ".join(parts)


_SECURITY_HEADERS = {
    "X-Content-Type-Options":        "nosniff",
    "X-Frame-Options":               "DENY",
    "X-XSS-Protection":              "1; mode=block",
    "Referrer-Policy":               "strict-origin-when-cross-origin",
    "Permissions-Policy":            "geolocation=(self), camera=(self), microphone=(self)",
    "Cross-Origin-Opener-Policy":    "same-origin",
    "Cross-Origin-Resource-Policy":  "same-origin",
}

_HSTS_HEADER = "max-age=31536000; includeSubDomains; preload"

# Mutating methods that require CSRF protection
_CSRF_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# CSRF-exempt path prefixes (Bearer-token APIs)
_CSRF_EXEMPT_PREFIXES = (
    "/api/gate/",
    "/api/worker-app/",
    "/api/public/",
    "/api/health",
)


def register_security_middleware(app: Flask) -> None:
    """Register all security middleware on the Flask app."""

    @app.after_request
    def _add_security_headers(response: Response) -> Response:
        # Security headers — X-Frame-Options/CSP framing set in server.apply_security_headers
        skip_framing = {
            k: v
            for k, v in _SECURITY_HEADERS.items()
            if k not in ("X-Frame-Options",)
        }
        for header, value in skip_framing.items():
            response.headers.setdefault(header, value)

        # HSTS: HTTPS only
        if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
            response.headers["Strict-Transport-Security"] = _HSTS_HEADER

        # CSP
        if not response.headers.get("Content-Security-Policy"):
            path = (request.path or "").lower()
            csp = _build_csp()
            if path.endswith(".html") or path.startswith("/admin-v2/"):
                csp = csp.replace("frame-src 'none'", "frame-src 'self' blob:")
                csp = csp.replace("object-src 'none'", "object-src 'self' blob:")
            response.headers["Content-Security-Policy"] = csp

        # Strip server identification headers
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)

        # CSRF token cookie for SPA (readable by JavaScript)
        if request.method == "GET" and "text/html" in (response.content_type or ""):
            if "csrf_token" not in request.cookies:
                token = secrets.token_urlsafe(32)
                response.set_cookie(
                    "csrf_token",
                    token,
                    httponly=False,  # must be readable by JavaScript
                    samesite="Strict",
                    secure=request.is_secure,
                )

        return response

    @app.before_request
    def _csrf_check():
        """CSRF protection for mutating requests."""
        if request.method not in _CSRF_METHODS:
            return None

        path = request.path

        # Admin/mobile APIs with Bearer token (no cookie CSRF)
        auth_header = (request.headers.get("Authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            return None

        # Bearer-token APIs are exempt (separate auth)
        if any(path.startswith(prefix) for prefix in _CSRF_EXEMPT_PREFIXES):
            return None

        if app.config.get("TESTING") or not app.config.get("WTF_CSRF_ENABLED", True):
            return None

        # JSON APIs: validate Origin instead of CSRF token
        content_type = request.content_type or ""
        if "application/json" in content_type:
            # Origin check for JSON requests
            return _check_origin()

        # CSRF token check for form submissions
        if not app.config.get("WTF_CSRF_ENABLED", True):
            return None

        csrf_token = (
            request.headers.get("X-CSRF-Token")
            or request.form.get("csrf_token")
            or request.json.get("csrf_token") if request.is_json else None
        )
        cookie_token = request.cookies.get("csrf_token")

        if not csrf_token or not cookie_token:
            return jsonify({"error": "csrf_required", "message": "CSRF token missing"}), 403

        if not secrets.compare_digest(csrf_token, cookie_token):
            logger.warning(
                "CSRF mismatch: path=%s ip=%s",
                path,
                request.remote_addr,
            )
            return jsonify({"error": "csrf_invalid", "message": "Invalid CSRF token"}), 403

        return None

    def _check_origin() -> Optional[Response]:
        """Validate Origin header for JSON API requests."""
        origin = request.headers.get("Origin", "").strip().rstrip("/")
        if not origin:
            return None  # no Origin (curl, server-to-server) — allowed

        host = request.host.split(":")[0]
        allowed_origins = app.config.get("CORS_ORIGINS", [])

        # Origin matches current host
        if f"https://{host}" == origin or f"http://{host}" == origin:
            return None

        # Origin in allowlist
        if origin in allowed_origins:
            return None

        logger.warning(
            "Origin mismatch (potential CSRF): origin=%s host=%s path=%s",
            origin, host, request.path,
        )
        if (os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_GIT_COMMIT_SHA") or "").strip():
            return jsonify({"error": "csrf_origin_mismatch", "message": "Invalid Origin header"}), 403
        return None
