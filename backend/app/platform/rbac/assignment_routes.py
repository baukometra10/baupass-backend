"""Assign enterprise roles to users (Phase B)."""
from __future__ import annotations

import secrets

from flask import Blueprint, g, jsonify, request

rbac_assign_bp = Blueprint("rbac_assign", __name__)


def register_rbac_assignment_blueprint(flask_app) -> None:
    from backend.server import get_db, now_iso, require_auth, require_roles

    @rbac_assign_bp.get("/platform/rbac/users/<user_id>/roles")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def list_user_roles(user_id):
        from backend.app.platform.rbac.enforcement import load_user_enterprise_roles

        db = get_db()
        actor = g.current_user
        target_user = db.execute("SELECT id, username, role, company_id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target_user:
            return jsonify({"error": "user_not_found"}), 404
        if actor.get("role") != "superadmin" and str(target_user["company_id"] or "") != str(
            actor.get("company_id") or ""
        ):
            return jsonify({"error": "forbidden"}), 403
        roles = load_user_enterprise_roles(db, dict(target_user))
        return jsonify({"userId": user_id, "enterpriseRoles": roles, "legacyRole": target_user["role"]})

    @rbac_assign_bp.post("/platform/rbac/users/<user_id>/roles")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def assign_role(user_id):
        from backend.app.platform.rbac.catalog import ENTERPRISE_ROLES

        payload = request.get_json(silent=True) or {}
        role_id = str(payload.get("roleId") or "").strip()
        valid_ids = {r["id"] for r in ENTERPRISE_ROLES}
        if role_id not in valid_ids:
            return jsonify({"error": "invalid_role_id"}), 400

        db = get_db()
        target = db.execute("SELECT id, company_id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            return jsonify({"error": "user_not_found"}), 404
        actor = g.current_user
        company_id = str(target["company_id"] or "")
        if actor.get("role") != "superadmin" and company_id != str(actor.get("company_id") or ""):
            return jsonify({"error": "forbidden"}), 403

        era_id = f"era-{secrets.token_hex(8)}"
        db.execute(
            """
            INSERT INTO enterprise_role_assignments
            (id, user_id, company_id, role_id, scope_type, scope_id, source, created_at)
            VALUES (?, ?, ?, ?, 'company', ?, 'manual', ?)
            """,
            (era_id, user_id, company_id or None, role_id, company_id or None, now_iso()),
        )
        db.commit()
        return jsonify({"ok": True, "assignmentId": era_id, "roleId": role_id})

    @rbac_assign_bp.delete("/platform/rbac/users/<user_id>/roles/<role_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def revoke_role(user_id, role_id):
        db = get_db()
        target = db.execute("SELECT company_id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            return jsonify({"error": "user_not_found"}), 404
        if g.current_user.get("role") != "superadmin" and str(target["company_id"]) != str(
            g.current_user.get("company_id") or ""
        ):
            return jsonify({"error": "forbidden"}), 403
        db.execute(
            "DELETE FROM enterprise_role_assignments WHERE user_id = ? AND role_id = ?",
            (user_id, role_id),
        )
        db.commit()
        return jsonify({"ok": True})

    @rbac_assign_bp.post("/platform/rbac/entra-group-mappings")
    @require_auth
    @require_roles("superadmin")
    def upsert_entra_mapping():
        payload = request.get_json(silent=True) or {}
        group_id = str(payload.get("entraGroupId") or "").strip()
        role_id = str(payload.get("enterpriseRoleId") or "").strip()
        company_id = str(payload.get("companyId") or "").strip() or None
        name = str(payload.get("entraGroupName") or "")[:200]
        if not group_id or not role_id:
            return jsonify({"error": "missing_fields"}), 400
        db = get_db()
        mid = f"egm-{secrets.token_hex(8)}"
        db.execute(
            """
            INSERT INTO entra_group_role_mappings (id, company_id, entra_group_id, entra_group_name, enterprise_role_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (mid, company_id, group_id, name, role_id, now_iso()),
        )
        db.commit()
        return jsonify({"ok": True, "id": mid})

    flask_app.register_blueprint(rbac_assign_bp, url_prefix="/api")
