"""Shared domain helpers."""
from __future__ import annotations

from flask import g, jsonify, request


def company_id_from_user(*, allow_query: bool = True) -> str | None:
    user = getattr(g, "current_user", None) or {}
    if user.get("role") == "superadmin" and allow_query:
        raw = request.args.get("company_id", "").strip()
        if raw:
            return raw
    cid = user.get("company_id")
    return str(cid) if cid else None


def forbidden_company():
    return jsonify({"error": "company_required"}), 400
