"""Shared domain helpers."""
from __future__ import annotations

from flask import g, jsonify, request


def company_id_from_user(*, allow_query: bool = True) -> str | None:
    user = getattr(g, "current_user", None) or {}
    if user.get("role") == "superadmin":
        raw = ""
        if allow_query:
            raw = str(request.args.get("company_id") or "").strip()
        if not raw:
            raw = str(
                getattr(g, "preview_company_id", None) or user.get("preview_company_id") or ""
            ).strip()
        if not raw and request.is_json:
            body = request.get_json(silent=True) or {}
            raw = str(body.get("company_id") or body.get("companyId") or "").strip()
        return raw or None
    cid = user.get("company_id")
    return str(cid) if cid else None


def forbidden_company():
    return jsonify({"error": "company_required"}), 400
