"""
Zero-Trust middleware — device fingerprint + optional mTLS header checks.
"""
from __future__ import annotations

import hashlib
import os

from flask import Flask, g, jsonify, request


def register_zero_trust_middleware(flask_app: Flask) -> None:
    if os.getenv("BAUPASS_ZERO_TRUST", "").strip() not in {"1", "true", "yes"}:
        return

    @flask_app.before_request
    def _zero_trust_check():
        if not request.path.startswith("/api/"):
            return None
        if request.path.startswith("/api/health") or request.path in {"/metrics", "/observability/status"}:
            return None
        expected = os.getenv("BAUPASS_ZERO_TRUST_TOKEN", "").strip()
        if expected and request.headers.get("X-Zero-Trust-Token", "") != expected:
            return jsonify({"error": "zero_trust_denied"}), 403
        fp = request.headers.get("X-Device-Fingerprint", "")
        if fp:
            g.device_fingerprint = hashlib.sha256(fp.encode()).hexdigest()[:32]
        token = ""
        auth = (request.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        if not token:
            token = (request.cookies.get("baupass_session") or "").strip()
        if token:
            try:
                from backend.server import get_db
                from backend.app.platform.security.session_devices import session_device_allowed

                allowed, reason = session_device_allowed(get_db(), token=token, req=request)
                if not allowed:
                    return jsonify({"error": reason or "zero_trust_device_denied"}), 403
            except Exception:
                pass
        return None
