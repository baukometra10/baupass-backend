"""
Public API v1 — developer keys, webhooks management, read-only workforce API shell.
"""
from __future__ import annotations

from flask import Blueprint, Flask, g, jsonify, request

from .api_keys import create_api_key, list_api_keys, revoke_api_key
from .auth import require_api_key
from .webhooks import create_webhook_endpoint, delete_webhook_endpoint, list_webhook_endpoints

api_v1_bp = Blueprint("api_v1", __name__)
api_platform_bp = Blueprint("api_platform", __name__)


def _company_id_from_session() -> int:
    user = g.current_user
    if user.get("role") == "superadmin":
        raw = request.args.get("company_id", "").strip()
        if raw.isdigit():
            return int(raw)
        return int(user.get("company_id") or 0)
    return int(user.get("company_id") or 0)


# ── Public (API key) ─────────────────────────────────────────────────────────

@api_v1_bp.get("/public/health")
def v1_public_health():
    return jsonify({"ok": True, "version": "v1"})


@api_v1_bp.get("/company")
@require_api_key("read")
def v1_company_info():
    from backend.server import get_db

    db = get_db()
    row = db.execute(
        "SELECT id, name, status, plan, access_mode FROM companies WHERE id = ?",
        (g.api_company_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"company": dict(row)})


@api_v1_bp.get("/workers")
@require_api_key("read")
def v1_list_workers():
    from backend.server import get_db

    db = get_db()
    rows = db.execute(
        """
        SELECT id, badge_id, first_name, last_name, status
        FROM workers
        WHERE company_id = ? AND deleted_at IS NULL
        ORDER BY last_name, first_name
        LIMIT 500
        """,
        (g.api_company_id,),
    ).fetchall()
    return jsonify({"workers": [dict(r) for r in rows]})


@api_v1_bp.get("/access-logs/recent")
@require_api_key("read")
def v1_recent_access_logs():
    from backend.server import get_db

    limit = min(100, max(1, int(request.args.get("limit", "25"))))
    db = get_db()
    rows = db.execute(
        """
        SELECT al.id, al.worker_id, al.direction, al.gate, al.timestamp, w.badge_id
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ?
        ORDER BY al.timestamp DESC
        LIMIT ?
        """,
        (g.api_company_id, limit),
    ).fetchall()
    return jsonify({"access_logs": [dict(r) for r in rows]})


# ── Admin session — API keys & webhooks ─────────────────────────────────────

def _register_admin_routes():
    from backend.server import require_auth, require_roles

    @api_platform_bp.get("/developer/api-keys")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_list_api_keys():
        from backend.server import get_db

        cid = _company_id_from_session()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        return jsonify({"api_keys": list_api_keys(get_db(), cid)})

    @api_platform_bp.post("/developer/api-keys")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_create_api_key():
        from backend.server import get_db

        cid = _company_id_from_session()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()
        if not name:
            return jsonify({"error": "name_required"}), 400
        scopes = str(data.get("scopes", "read")).strip() or "read"
        result = create_api_key(
            get_db(),
            company_id=cid,
            name=name,
            scopes=scopes,
            created_by_user_id=str(g.current_user.get("id", "")),
            expires_at=data.get("expires_at"),
        )
        return jsonify(result), 201

    @api_platform_bp.delete("/developer/api-keys/<key_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_revoke_api_key(key_id: str):
        from backend.server import get_db

        cid = _company_id_from_session()
        if not revoke_api_key(get_db(), cid, key_id):
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True})

    @api_platform_bp.get("/developer/webhooks")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_list_webhooks():
        from backend.server import get_db

        cid = _company_id_from_session()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        return jsonify({"webhooks": list_webhook_endpoints(get_db(), cid)})

    @api_platform_bp.post("/developer/webhooks")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_create_webhook():
        from backend.server import get_db

        cid = _company_id_from_session()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        data = request.get_json(silent=True) or {}
        url = str(data.get("url", "")).strip()
        events = data.get("events") or []
        if not url or not isinstance(events, list):
            return jsonify({"error": "url_and_events_required"}), 400
        result = create_webhook_endpoint(get_db(), company_id=cid, url=url, events=events)
        return jsonify(result), 201

    @api_platform_bp.delete("/developer/webhooks/<endpoint_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_revoke_webhook(endpoint_id: str):
        from backend.server import get_db

        cid = _company_id_from_session()
        if not delete_webhook_endpoint(get_db(), cid, endpoint_id):
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True})


def register_api_platform_blueprints(flask_app: Flask) -> None:
    _register_admin_routes()
    flask_app.register_blueprint(api_v1_bp, url_prefix="/api/v1")
    flask_app.register_blueprint(api_platform_bp, url_prefix="/api")
