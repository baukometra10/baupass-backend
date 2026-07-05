from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from .._routes import register_blueprint_once
from ..shared import company_id_from_user, forbidden_company
from backend.app.platform.security.e2e_identity import E2EIdentityService, assert_no_private_key_material

e2e_bp = Blueprint("e2e_domain", __name__)


def register_e2e_blueprint(flask_app) -> None:
    from backend.server import get_db, require_auth, require_roles, require_worker_session

    def _worker_identity():
        worker = getattr(g, "worker", None) or {}
        worker_id = str(worker.get("id") or "").strip()
        company_id = str(worker.get("company_id") or "").strip()
        if not worker_id or not company_id:
            return None, None
        return worker_id, company_id

    @e2e_bp.put("/e2e/identity/me")
    @require_worker_session
    def worker_register_e2e_identity():
        worker_id, company_id = _worker_identity()
        if not worker_id:
            return jsonify({"error": "worker_context_missing"}), 401
        data = request.get_json(silent=True) or {}
        try:
            assert_no_private_key_material(data)
            pub = str(data.get("publicKeySpkiB64") or data.get("public_key_spki_b64") or "").strip()
            record = E2EIdentityService(get_db()).upsert_identity(
                entity_type="worker",
                entity_id=worker_id,
                company_id=company_id,
                public_key_spki_b64=pub,
                algorithm=str(data.get("algorithm") or "X25519"),
            )
            return jsonify({"ok": True, "identity": record})
        except ValueError as exc:
            code = str(exc)
            status = 403 if code == "private_key_forbidden" else 400
            return jsonify({"error": code}), status

    @e2e_bp.get("/e2e/identity/me")
    @require_worker_session
    def worker_get_e2e_identity():
        worker_id, _company_id = _worker_identity()
        if not worker_id:
            return jsonify({"error": "worker_context_missing"}), 401
        record = E2EIdentityService(get_db()).get_identity("worker", worker_id)
        if not record:
            return jsonify({"identity": None})
        return jsonify({"identity": record})

    @e2e_bp.get("/e2e/identity/public-keys")
    @require_worker_session
    def worker_list_e2e_public_keys():
        worker_id, company_id = _worker_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        keys = E2EIdentityService(get_db()).list_company_chat_keys(company_id, worker_id=worker_id)
        return jsonify({"publicKeys": keys})

    @e2e_bp.put("/e2e/identity/admin/me")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_register_e2e_identity():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        data = request.get_json(silent=True) or {}
        try:
            assert_no_private_key_material(data)
            user_id = str(g.current_user.get("id") or "").strip()
            if not user_id:
                return jsonify({"error": "user_required"}), 400
            pub = str(data.get("publicKeySpkiB64") or data.get("public_key_spki_b64") or "").strip()
            record = E2EIdentityService(get_db()).upsert_identity(
                entity_type="user",
                entity_id=user_id,
                company_id=cid,
                public_key_spki_b64=pub,
                algorithm=str(data.get("algorithm") or "X25519"),
            )
            return jsonify({"ok": True, "identity": record})
        except ValueError as exc:
            code = str(exc)
            status = 403 if code == "private_key_forbidden" else 400
            return jsonify({"error": code}), status

    @e2e_bp.get("/e2e/identity/admin/me")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_get_e2e_identity():
        user_id = str(g.current_user.get("id") or "").strip()
        if not user_id:
            return jsonify({"error": "user_required"}), 400
        record = E2EIdentityService(get_db()).get_identity("user", user_id)
        if not record:
            return jsonify({"identity": None})
        return jsonify({"identity": record})

    @e2e_bp.get("/e2e/identity/admin/public-keys")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_list_e2e_public_keys():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        worker_id = str(request.args.get("worker_id") or "").strip() or None
        keys = E2EIdentityService(get_db()).list_company_chat_keys(cid, worker_id=worker_id)
        return jsonify({"publicKeys": keys})

    @e2e_bp.post("/e2e/identity/me/rotate")
    @require_worker_session
    def worker_rotate_e2e_identity():
        worker_id, company_id = _worker_identity()
        if not worker_id:
            return jsonify({"error": "worker_context_missing"}), 401
        data = request.get_json(silent=True) or {}
        try:
            assert_no_private_key_material(data)
            pub = str(data.get("publicKeySpkiB64") or data.get("public_key_spki_b64") or "").strip()
            record = E2EIdentityService(get_db()).upsert_identity(
                entity_type="worker",
                entity_id=worker_id,
                company_id=company_id,
                public_key_spki_b64=pub,
                algorithm=str(data.get("algorithm") or "X25519"),
            )
            return jsonify({"ok": True, "identity": record, "rotated": True})
        except ValueError as exc:
            code = str(exc)
            status = 403 if code == "private_key_forbidden" else 400
            return jsonify({"error": code}), status

    @e2e_bp.post("/e2e/identity/admin/me/rotate")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_rotate_e2e_identity():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        data = request.get_json(silent=True) or {}
        try:
            assert_no_private_key_material(data)
            user_id = str(g.current_user.get("id") or "").strip()
            pub = str(data.get("publicKeySpkiB64") or data.get("public_key_spki_b64") or "").strip()
            record = E2EIdentityService(get_db()).upsert_identity(
                entity_type="user",
                entity_id=user_id,
                company_id=cid,
                public_key_spki_b64=pub,
                algorithm=str(data.get("algorithm") or "X25519"),
            )
            return jsonify({"ok": True, "identity": record, "rotated": True})
        except ValueError as exc:
            code = str(exc)
            status = 403 if code == "private_key_forbidden" else 400
            return jsonify({"error": code}), status

    register_blueprint_once(flask_app, e2e_bp, url_prefix="/api")
    print("[baupass] domain/e2e: public-key identity routes registered", flush=True)
