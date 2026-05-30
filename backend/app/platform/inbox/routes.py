"""Inbox API — /api/inbox"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

inbox_bp = Blueprint("platform_inbox", __name__)


def register_inbox_blueprint(flask_app) -> None:
    from backend.server import get_db, require_auth, require_roles

    @inbox_bp.get("/inbox")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def get_inbox():
        from .service import build_operations_inbox

        role = str(g.current_user.get("role") or "company-admin")
        company_id = str(g.current_user.get("company_id") or "").strip()
        if role == "superadmin":
            company_id = str(request.args.get("company_id") or company_id or "").strip() or None
        limit = min(max(int(request.args.get("limit", "80")), 1), 200)
        include_resolved = request.args.get("include_resolved", "").lower() in {"1", "true", "yes"}
        source_filter = str(request.args.get("source") or "").strip() or None
        try:
            dash = build_operations_inbox(
                get_db(),
                company_id,
                role=role,
                limit=limit,
                include_resolved=include_resolved,
                source_filter=source_filter,
            )
        except Exception as exc:
            return jsonify({"error": "inbox_build_failed", "message": str(exc)}), 500
        return jsonify(dash)

    @inbox_bp.get("/inbox/counts")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def inbox_counts():
        from .service import build_operations_inbox

        role = str(g.current_user.get("role") or "company-admin")
        company_id = str(g.current_user.get("company_id") or "").strip()
        if role == "superadmin":
            company_id = str(request.args.get("company_id") or company_id or "").strip() or None
        try:
            dash = build_operations_inbox(get_db(), company_id, role=role, limit=10)
        except Exception as exc:
            return jsonify({"error": "inbox_build_failed", "message": str(exc)}), 500
        return jsonify({"counts": dash.get("counts", {}), "companyId": dash.get("companyId")})

    @inbox_bp.post("/inbox/<path:item_id>/resolve")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def resolve_item(item_id: str):
        from .service import resolve_inbox_item

        role = str(g.current_user.get("role") or "company-admin")
        company_id = str(g.current_user.get("company_id") or "").strip()
        if role == "superadmin":
            data = request.get_json(silent=True) or {}
            company_id = str(request.args.get("company_id") or data.get("company_id") or company_id)
        user_id = str(g.current_user.get("id") or g.current_user.get("username") or "")
        data = request.get_json(silent=True) or {}
        decision = str(data.get("decision") or "").strip() or None
        result = resolve_inbox_item(
            get_db(),
            item_id=item_id,
            company_id=company_id,
            user_id=user_id,
            decision=decision,
        )
        code = 200 if result.get("ok") else 400
        return jsonify(result), code

    @inbox_bp.post("/inbox/bulk")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def inbox_bulk():
        from .bulk import run_bulk_inbox_action

        role = str(g.current_user.get("role") or "company-admin")
        company_id = str(g.current_user.get("company_id") or "").strip()
        data = request.get_json(silent=True) or {}
        if role == "superadmin":
            company_id = str(
                request.args.get("company_id") or data.get("company_id") or company_id
            ).strip()
        action = str(data.get("action") or "").strip()
        item_ids = data.get("item_ids") if isinstance(data.get("item_ids"), list) else None
        decision = str(data.get("decision") or "approve").strip()
        user_id = str(g.current_user.get("id") or g.current_user.get("username") or "")
        result = run_bulk_inbox_action(
            db=get_db(),
            company_id=company_id,
            user_id=user_id,
            action=action,
            item_ids=item_ids,
            decision=decision,
        )
        return jsonify(result), 200 if result.get("ok") else 400

    if "platform_inbox" not in flask_app.blueprints:
        flask_app.register_blueprint(inbox_bp, url_prefix="/api")
