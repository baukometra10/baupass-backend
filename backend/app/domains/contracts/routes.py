from __future__ import annotations

import io
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
    import os
    import threading

    from backend.app.platform.plan_guard import require_plan_capability
    from backend.server import BASE_DIR, get_db, require_auth, require_roles, require_worker_session

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

    @contracts_core_bp.post("/contracts/<contract_id>/regenerate")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def regenerate_contract_draft(contract_id: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data)
        if not cid:
            return forbidden_company()
        service = ContractsService(get_db())
        try:
            result = service.rebuild_contract_draft(
                contract_id,
                cid,
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
        service = ContractsService(get_db())
        try:
            contract = service.update_contract(
                contract_id,
                cid,
                final_text=final_text,
                payload=data,
                actor_user_id=str(g.current_user.get("id") or ""),
            )
        except ValueError as exc:
            code = str(exc)
            if code.startswith("missing_fields:"):
                return jsonify({"error": "missing_fields", "fields": code.split(":", 1)[1].split(",")}), 400
            return jsonify({"error": code}), 400
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
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data)
        if not cid:
            return forbidden_company()
        storage_root = Path(BASE_DIR) / "backend" / "uploads"
        try:
            contract, _pdf_bytes, file_path = ContractsService(get_db()).generate_contract_pdf(
                contract_id, cid, storage_root, payload=data
            )
        except ValueError as exc:
            code = str(exc)
            if code.startswith("missing_fields:"):
                return jsonify({"error": "missing_fields", "fields": code.split(":", 1)[1].split(",")}), 400
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

    @contracts_core_bp.post("/contracts/<contract_id>/sign-link")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def create_contract_sign_link(contract_id: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data)
        if not cid:
            return forbidden_company()
        role = str(data.get("role") or "employee").strip().lower()
        renew = bool(data.get("renew"))
        send_email = bool(data.get("send_email") or data.get("sendEmail"))
        try:
            service = ContractsService(get_db())
            if send_email:
                result = service.send_sign_invite_email(
                    contract_id,
                    cid,
                    role=role,
                    actor_user_id=str(g.current_user.get("id") or ""),
                    email=str(data.get("email") or "").strip() or None,
                    renew=renew,
                    base_url=str(request.host_url or "").rstrip("/"),
                    payload=data,
                )
            else:
                result = service.create_sign_invite(
                    contract_id,
                    cid,
                    role=role,
                    actor_user_id=str(g.current_user.get("id") or ""),
                    renew=renew,
                    payload=data,
                )
                base = str(request.host_url or "").rstrip("/")
                result = {**result, "absoluteUrl": f"{base}{result['signUrl']}"}
                if role == "employee":
                    contract = service.get_contract(contract_id, cid)
                    worker_id = (contract or {}).get("worker_id")
                    if contract and worker_id:
                        service._push_contract_sign_invite(
                            str(worker_id), contract, result["absoluteUrl"]
                        )
        except ValueError as exc:
            code = str(exc)
            if code.startswith("missing_fields:"):
                return jsonify({"error": "missing_fields", "fields": code.split(":", 1)[1].split(",")}), 400
            status = 404 if code == "contract_not_found" else 400
            return jsonify({"error": code}), status
        return jsonify(result)

    @contracts_core_bp.get("/workers/<worker_id>/employment-contracts")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def list_worker_employment_contracts(worker_id: str):
        cid = _resolve_company_id()
        if not cid:
            return forbidden_company()
        contracts = ContractsService(get_db()).list_contracts_for_worker(worker_id, cid)
        return jsonify({"contracts": contracts})

    @contracts_core_bp.post("/contracts/<contract_id>/sign-link/email")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def email_contract_sign_link(contract_id: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data)
        if not cid:
            return forbidden_company()
        role = str(data.get("role") or "employee").strip().lower()
        try:
            result = ContractsService(get_db()).send_sign_invite_email(
                contract_id,
                cid,
                role=role,
                actor_user_id=str(g.current_user.get("id") or ""),
                email=str(data.get("email") or "").strip() or None,
                renew=bool(data.get("renew")),
                base_url=str(request.host_url or "").rstrip("/"),
                payload=data,
            )
        except ValueError as exc:
            code = str(exc)
            if code.startswith("missing_fields:"):
                return jsonify({"error": "missing_fields", "fields": code.split(":", 1)[1].split(",")}), 400
            status = 404 if code == "contract_not_found" else 400
            return jsonify({"error": code}), status
        return jsonify(result)

    @contracts_core_bp.post("/contracts/<contract_id>/sign-link/sms")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def sms_contract_sign_link(contract_id: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data)
        if not cid:
            return forbidden_company()
        role = str(data.get("role") or "employee").strip().lower()
        try:
            result = ContractsService(get_db()).send_sign_invite_sms(
                contract_id,
                cid,
                role=role,
                actor_user_id=str(g.current_user.get("id") or ""),
                phone=str(data.get("phone") or "").strip() or None,
                renew=bool(data.get("renew")),
                base_url=str(request.host_url or "").rstrip("/"),
                payload=data,
            )
        except ValueError as exc:
            code = str(exc)
            if code.startswith("missing_fields:"):
                return jsonify({"error": "missing_fields", "fields": code.split(":", 1)[1].split(",")}), 400
            status = 404 if code == "contract_not_found" else 400
            return jsonify({"error": code}), status
        return jsonify(result)

    @contracts_core_bp.get("/contracts/<contract_id>/events")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def list_contract_events(contract_id: str):
        cid = _resolve_company_id()
        if not cid:
            return forbidden_company()
        events = ContractsService(get_db()).list_contract_events(contract_id, cid)
        return jsonify({"events": events})

    @contracts_core_bp.get("/contracts/<contract_id>/sign-sessions")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def list_contract_sign_sessions(contract_id: str):
        cid = _resolve_company_id()
        if not cid:
            return forbidden_company()
        sessions = ContractsService(get_db()).list_sign_sessions(contract_id, cid)
        return jsonify({"sessions": sessions})

    @contracts_core_bp.get("/public/contracts/sign/<token>")
    def public_contract_sign_view(token: str):
        view = ContractsService(get_db()).get_public_sign_view(token)
        if not view:
            return jsonify({"error": "sign_session_not_found"}), 404
        if view.get("error"):
            return jsonify(view), 410
        return jsonify(view)

    @contracts_core_bp.post("/public/contracts/sign/<token>")
    def public_contract_sign_submit(token: str):
        data = request.get_json(silent=True) or {}
        storage_root = Path(BASE_DIR) / "backend" / "uploads"
        lat = data.get("sign_latitude", data.get("signLatitude"))
        lng = data.get("sign_longitude", data.get("signLongitude"))
        try:
            lat_f = float(lat) if lat not in (None, "") else None
        except (TypeError, ValueError):
            lat_f = None
        try:
            lng_f = float(lng) if lng not in (None, "") else None
        except (TypeError, ValueError):
            lng_f = None
        try:
            result = ContractsService(get_db()).submit_public_signature(
                token,
                signer_name=str(data.get("signer_name") or data.get("signerName") or ""),
                signature_data=str(data.get("signature_data") or data.get("signatureData") or ""),
                sign_place=str(data.get("sign_place") or data.get("signPlace") or ""),
                storage_root=storage_root,
                consent_accepted=bool(data.get("consent_accepted") or data.get("consentAccepted")),
                sign_latitude=lat_f,
                sign_longitude=lng_f,
            )
        except ValueError as exc:
            code = str(exc)
            status = 404 if code == "sign_session_not_found" else 400
            if code == "sign_link_expired":
                status = 410
            return jsonify({"error": code}), status
        return jsonify(result)

    @contracts_core_bp.get("/public/contracts/sign/<token>/preview.pdf")
    def public_contract_sign_preview(token: str):
        try:
            pdf_bytes = ContractsService(get_db()).build_public_preview_pdf_bytes(token)
        except ValueError as exc:
            code = str(exc)
            status = 404 if code == "sign_session_not_found" else 410 if code == "sign_link_expired" else 400
            return jsonify({"error": code}), status
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=False,
            download_name="contract-preview.pdf",
        )

    @contracts_core_bp.get("/public/contracts/sign/<token>/download.pdf")
    def public_contract_sign_download(token: str):
        service = ContractsService(get_db())
        session = service.repo.get_sign_session_by_token(token)
        if not session or str(session.get("status") or "") != "signed":
            return jsonify({"error": "signed_pdf_not_ready"}), 404
        contract = service.get_contract(str(session["contract_id"]), str(session["company_id"]))
        if not contract:
            return jsonify({"error": "contract_not_found"}), 404
        file_path = Path(str(contract.get("pdf_file_path") or ""))
        if not file_path.exists():
            return jsonify({"error": "contract_pdf_missing"}), 404
        return send_file(file_path, mimetype="application/pdf", as_attachment=True, download_name=f"{contract['id']}.pdf")

    @contracts_core_bp.get("/contracts/<contract_id>/preview.pdf")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def preview_contract_pdf(contract_id: str):
        cid = _resolve_company_id()
        if not cid:
            return forbidden_company()
        try:
            pdf_bytes = ContractsService(get_db()).build_preview_pdf_bytes(contract_id, cid)
        except ValueError as exc:
            code = str(exc)
            return jsonify({"error": code}), 404 if code == "contract_not_found" else 400
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=False,
            download_name=f"{contract_id}-preview.pdf",
        )

    @contracts_core_bp.get("/contracts/integrations-status")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("employment_contracts")
    def contract_integrations_status():
        cid = _resolve_company_id()
        if not cid:
            return forbidden_company()
        return jsonify(ContractsService(get_db()).get_integrations_status(cid))

    @contracts_core_bp.get("/worker-app/employment-contracts")
    @require_worker_session
    def worker_app_employment_contracts():
        worker_id = str(g.worker["id"])
        company_id = str(g.worker["company_id"])
        base = str(request.host_url or "").rstrip("/")
        contracts = ContractsService(get_db()).list_worker_app_contracts(worker_id, company_id, base_url=base)
        return jsonify({"contracts": contracts})

    _testing = str(os.getenv("BAUPASS_ENV", "")).strip().lower() == "testing"
    _bg_jobs = str(os.getenv("BAUPASS_ENABLE_BACKGROUND_JOBS", "1")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if (
        _bg_jobs
        and not _testing
        and not flask_app.config.get("TESTING")
        and not getattr(flask_app, "_contract_reminder_thread_started", False)
    ):
        from .reminders import contract_reminder_loop

        base_url = str(getattr(flask_app, "config", {}).get("PUBLIC_BASE_URL") or "")
        threading.Thread(
            target=contract_reminder_loop,
            args=(flask_app, get_db, base_url),
            name="baupass-contract-reminders",
            daemon=True,
        ).start()  # baupass:allow-inline-thread
        flask_app._contract_reminder_thread_started = True

    register_blueprint_once(flask_app, contracts_core_bp, url_prefix="/api")
    print("[baupass] domain/contracts: templates, drafts, contracts, pdf, sign routes registered", flush=True)
