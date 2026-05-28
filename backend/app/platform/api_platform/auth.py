"""
API key authentication for public developer API.
"""
from __future__ import annotations

from functools import wraps

from flask import g, jsonify, request

from .api_keys import authenticate_api_key


def require_api_key(scopes: str | None = None):
    """Authenticate X-Api-Key header against developer_api_keys."""

    def decorator(handler):
        @wraps(handler)
        def wrapper(*args, **kwargs):
            raw = (request.headers.get("X-Api-Key") or request.headers.get("Authorization", "")).strip()
            if raw.lower().startswith("bearer "):
                raw = raw[7:].strip()
            if not raw:
                return jsonify({"error": "missing_api_key"}), 401
            from backend.server import get_db

            row = authenticate_api_key(get_db(), raw)
            if not row:
                return jsonify({"error": "invalid_api_key"}), 401
            if scopes:
                allowed = {s.strip() for s in (row.get("scopes") or "").split(",") if s.strip()}
                needed = {s.strip() for s in scopes.split(",") if s.strip()}
                if needed and not needed.issubset(allowed) and "*" not in allowed:
                    return jsonify({"error": "insufficient_scope"}), 403
            g.api_key = row
            g.api_company_id = str(row["company_id"] or "").strip()
            return handler(*args, **kwargs)

        return wrapper

    return decorator
