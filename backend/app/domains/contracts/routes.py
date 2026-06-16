from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Flask, g, jsonify, request, send_file

from .._routes import register_blueprint_once
from ..shared import company_id_from_user, forbidden_company
from .service import ContractsService

contracts_core_bp = Blueprint("contracts_domain_core", __name__)


def _resolve_company_id(data: dict | None = None) -> str:
    data = data or {}
    role = str(g.current_user.get("role") or "")
    if role == "superadmin":
        return str(data.get("company_id") or request.args.get("company_id") or "").strip()
    return str(g.current_user.get("company_id") or "").strip()


def register_contracts_blueprint(flask_app: Flask) -> None:
    from backend.app.platform.plan_guard import require_plan_capability
    from backend.server import BASE_DIR, get_db, require_auth, require_roles

    @contracts_core_bp.get("/contracts/templates")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def list_contract_templates():
        cid = _resolve_company_id()
        if not cid:
            return forbidden_company()
        service = ContractsService(get_db())
        return jsonify({"templates": service.bootstrap_templates(cid, actor_user_id=str(g.current_user.get("id") or ""))})

    @contracts_core_bp.post("/contracts/draft")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def create_contract_draft():
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data)
        if not cid:
            return forbidden_company()
        template_id = str(data.get("template_id") or "").strip()
        if not template_id:
            return jsonify({"error": "template_required"}), 400
        worker_id = str(data.get("worker_id") or "").strip() or None
        service = ContractsService(get_db())
        try:
            result = service.build_contract_draft(
                company_id=cid,
                template_id=template_id,
                worker_id=worker_id,
                actor_user_id=str(g.current_user.get("id") or ""),
                payload=data,
            )
            return jsonify(result)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @contracts_core_bp.get("/contracts")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def list_contracts():
        cid = _resolve_company_id()
        if not cid:
            return forbidden_company()
        return jsonify({"contracts": ContractsService(get_db()).list_contracts(cid)})

    @contracts_core_bp.get("/contracts/<contract_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def get_contract(contract_id: str):
        cid = _resolve_company_id()
        if not cid:
            return forbidden_company()
        contract = ContractsService(get_db()).get_contract(contract_id, cid)
        if not contract:
            return jsonify({"error": "contract_not_found"}), 404
        return jsonify(contract)

    @contracts_core_bp.put("/contracts/<contract_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def update_contract(contract_id: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data)
        if not cid:
            return forbidden_company()
        final_text = str(data.get("final_text") or "").strip()
        if not final_text:
            return jsonify({"error": "final_text_required"}), 400
        contract = ContractsService(get_db()).update_contract(contract_id, cid, final_text)
        if not contract:
            return jsonify({"error": "contract_not_found"}), 404
        return jsonify({"ok": True, "contract": contract})

    @contracts_core_bp.delete("/contracts/<contract_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def delete_contract(contract_id: str):
        cid = _resolve_company_id(request.get_json(silent=True) or {})
        if not cid:
            return forbidden_company()
        storage_root = Path(BASE_DIR) / "backend" / "uploads"
        deleted = ContractsService(get_db()).delete_contract(contract_id, cid, storage_root)
        if not deleted:
            return jsonify({"error": "contract_not_found"}), 404
        return jsonify({"ok": True})

    @contracts_core_bp.post("/contracts/<contract_id>/generate-pdf")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def generate_contract_pdf(contract_id: str):
        cid = _resolve_company_id(request.get_json(silent=True) or {})
        if not cid:
            return forbidden_company()
        storage_root = Path(BASE_DIR) / "backend" / "uploads"
        try:
            contract, _pdf_bytes, file_path = ContractsService(get_db()).generate_contract_pdf(contract_id, cid, storage_root)
        except ValueError as exc:
            code = str(exc)
            return jsonify({"error": code}), 404 if code == "contract_not_found" else 400
        return jsonify({"ok": True, "contract": contract, "download": f"/api/contracts/{contract_id}/download.pdf?company_id={cid}", "filePath": str(file_path)})

    @contracts_core_bp.get("/contracts/<contract_id>/download.pdf")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def download_contract_pdf(contract_id: str):
        cid = _resolve_company_id()
        if not cid:
            return forbidden_company()
        contract = ContractsService(get_db()).get_contract(contract_id, cid)
        if not contract:
            return jsonify({"error": "contract_not_found"}), 404
        file_path = Path(str(contract.get("pdf_file_path") or ""))
        if not file_path.exists():
            return jsonify({"error": "contract_pdf_missing"}), 404
        return send_file(file_path, mimetype="application/pdf", as_attachment=True, download_name=f"{contract_id}.pdf")

    register_blueprint_once(flask_app, contracts_core_bp, url_prefix="/api")
    print("[baupass] domain/contracts: templates, drafts, contracts, pdf routes registered", flush=True)
