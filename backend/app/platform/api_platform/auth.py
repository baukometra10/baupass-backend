"""
API key authentication for public developer API.
"""
from __future__ import annotations

from functools import wraps

from flask import g, jsonify, request

from .api_keys import authenticate_api_key


def require_api_key(scopes: str | None = None):
    """Authenticate developer API key, or WorkPass Lohn platform key + company header."""

    def decorator(handler):
        @wraps(handler)
        def wrapper(*args, **kwargs):
            from backend.server import get_db

            db = get_db()
            # 1) WorkPass Lohn shared key (WORKPASS_API_KEY / X-WorkPass-Key)
            try:
                from backend.app.platform.accounting.auth import (
                    authenticate_lohn_pull_request,
                    extract_lohn_api_key_from_headers,
                )

                company_id = (
                    request.headers.get("X-WorkPass-Company-Id")
                    or request.headers.get("X-Company-Id")
                    or request.args.get("company_id")
                    or request.args.get("companyId")
                    or ""
                ).strip()
                lohn_key = extract_lohn_api_key_from_headers(request.headers)
                if lohn_key and company_id:
                    integ = authenticate_lohn_pull_request(
                        db, company_id=company_id, api_key=lohn_key
                    )
                    if integ and integ.get("lohnDisabled"):
                        return jsonify(
                            {
                                "error": "workpass_lohn_disabled",
                                "hint": "WorkPass Lohn für diese Firma in der Plattform aktivieren",
                                "companyId": company_id,
                            }
                        ), 403
                    if integ:
                        g.api_key = {
                            "id": integ.get("id"),
                            "company_id": company_id,
                            "scopes": "read,*,lohn",
                            "authMode": integ.get("authMode") or "lohn",
                        }
                        g.api_company_id = company_id
                        g.lohn_bridge_auth = True
                        return handler(*args, **kwargs)
            except Exception:
                pass

            # 2) Developer API keys (original path)
            raw = (request.headers.get("X-Api-Key") or request.headers.get("Authorization", "")).strip()
            if raw.lower().startswith("bearer "):
                raw = raw[7:].strip()
            if not raw:
                return jsonify({"error": "missing_api_key"}), 401

            row = authenticate_api_key(db, raw)
            if not row:
                return jsonify(
                    {
                        "error": "invalid_api_key",
                        "hint": "Use developer X-Api-Key or WORKPASS_API_KEY + X-WorkPass-Company-Id",
                    }
                ), 401
            if scopes:
                allowed = {s.strip() for s in (row.get("scopes") or "").split(",") if s.strip()}
                needed = {s.strip() for s in scopes.split(",") if s.strip()}
                if needed and not needed.issubset(allowed) and "*" not in allowed:
                    return jsonify({"error": "insufficient_scope"}), 403
            g.api_key = row
            g.api_company_id = str(row["company_id"] or "").strip()
            g.lohn_bridge_auth = False
            return handler(*args, **kwargs)

        return wrapper

    return decorator
