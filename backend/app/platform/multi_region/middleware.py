"""Enforce tenant data residency when enabled."""
from __future__ import annotations

import os

from flask import Flask, g, jsonify, request


def register_data_residency_middleware(flask_app: Flask) -> None:
    if os.getenv("BAUPASS_ENFORCE_DATA_RESIDENCY", "0").strip().lower() not in {"1", "true", "yes"}:
        return

    @flask_app.before_request
    def _residency_check():
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return None
        if not request.path.startswith("/api/"):
            return None
        if request.path.startswith("/api/health"):
            return None
        user = getattr(g, "current_user", None) or {}
        cid = user.get("company_id")
        if not cid or user.get("role") == "superadmin":
            return None
        try:
            from backend.server import get_db
            from .residency import residency_allows_request

            allowed, reason = residency_allows_request(get_db(), str(cid))
            if not allowed:
                return jsonify({"error": reason}), 403
        except Exception:
            pass
        return None
