"""
Workers domain — legacy /api/workers routes + v2 API.
"""
from __future__ import annotations

from flask import Blueprint, Flask, jsonify, request

from .._routes import mount_rules_once, register_blueprint_once, register_blueprint_once
from ..shared import company_id_from_user, forbidden_company
from .service import WorkersService

workers_core_bp = Blueprint("workers_domain_core", __name__)
workers_v2_bp = Blueprint("workers_domain_v2", __name__)
_service = WorkersService()


def _register_core_worker_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted

    if routes_already_mounted("workers"):
        return
    from backend.server import (
        activate_worker_hce_device,
        bulk_delete_workers,
        bulk_update_worker_status,
        create_or_rotate_worker_identity_token,
        create_worker,
        create_worker_app_access,
        decide_photo_override_approval,
        delete_worker,
        delete_worker_document,
        download_worker_akte_pdf,
        download_worker_document,
        export_attendance_pdf,
        export_workers_csv,
        export_leave_request_pdf,
        export_workers_pdf,
        export_workers_signatures_zip,
        get_current_visitors,
        get_worker_app_access,
        get_worker_compliance_signature,
        create_worker_handover_sign_link,
        public_worker_handover_sign_view,
        public_worker_handover_sign_submit,
        get_worker_identity_token,
        import_workers_csv,
        list_pending_photo_override_approvals,
        list_worker_documents,
        list_worker_hce_devices,
        list_workers,
        put_worker_compliance_signature,
        reset_worker_pin,
        restore_worker,
        revoke_worker_hce_device,
        set_worker_identity_token_status,
        set_worker_lock,
        update_worker,
        upload_worker_document,
        validate_worker_photo,
        worker_badge_qr,
        worker_stats,
    )

    rules = (
        ("/workers/stats", worker_stats, ("GET",)),
        ("/workers/current-visitors", get_current_visitors, ("GET",)),
        ("/workers/photo-override-approvals/pending", list_pending_photo_override_approvals, ("GET",)),
        ("/workers/validate-photo", validate_worker_photo, ("POST",)),
        ("/workers/import-csv", import_workers_csv, ("POST",)),
        ("/workers/export.csv", export_workers_csv, ("GET",)),
        ("/workers/export.pdf", export_workers_pdf, ("GET",)),
        ("/workers/export.signatures.zip", export_workers_signatures_zip, ("GET",)),
        ("/workers/attendance.pdf", export_attendance_pdf, ("GET",)),
        ("/workers/bulk-status", bulk_update_worker_status, ("PATCH",)),
        ("/workers/bulk-delete", bulk_delete_workers, ("POST",)),
        ("/workers/photo-override-approvals/<approval_id>/decision", decide_photo_override_approval, ("POST",)),
        ("/workers", list_workers, ("GET",)),
        ("/workers", create_worker, ("POST",)),
        ("/workers/<worker_id>", update_worker, ("PUT",)),
        ("/workers/<worker_id>", delete_worker, ("DELETE",)),
        ("/workers/<worker_id>/compliance-signature", get_worker_compliance_signature, ("GET",)),
        ("/workers/<worker_id>/compliance-signature", put_worker_compliance_signature, ("PUT",)),
        ("/workers/<worker_id>/handover-sign-link", create_worker_handover_sign_link, ("POST",)),
        ("/public/workers/handover-sign/<token>", public_worker_handover_sign_view, ("GET",)),
        ("/public/workers/handover-sign/<token>", public_worker_handover_sign_submit, ("POST",)),
        ("/workers/<worker_id>/akte.pdf", download_worker_akte_pdf, ("GET",)),
        ("/workers/<worker_id>/restore", restore_worker, ("POST",)),
        ("/workers/<worker_id>/lock", set_worker_lock, ("POST",)),
        ("/workers/<worker_id>/reset-pin", reset_worker_pin, ("POST",)),
        ("/workers/<worker_id>/hce-devices", list_worker_hce_devices, ("GET",)),
        ("/workers/<worker_id>/hce-devices/<device_id>/revoke", revoke_worker_hce_device, ("POST",)),
        ("/workers/<worker_id>/hce-devices/<device_id>/activate", activate_worker_hce_device, ("POST",)),
        ("/workers/<worker_id>/app-access", get_worker_app_access, ("GET",)),
        ("/workers/<worker_id>/app-access", create_worker_app_access, ("POST",)),
        ("/workers/<worker_id>/qr.png", worker_badge_qr, ("GET",)),
        ("/workers/<worker_id>/identity-token", get_worker_identity_token, ("GET",)),
        ("/workers/<worker_id>/identity-token", create_or_rotate_worker_identity_token, ("POST",)),
        ("/workers/<worker_id>/identity-token/status", set_worker_identity_token_status, ("POST",)),
        ("/workers/<worker_id>/documents", list_worker_documents, ("GET",)),
        ("/workers/<worker_id>/documents/upload", upload_worker_document, ("POST",)),
        ("/workers/<worker_id>/documents/<doc_id>/download", download_worker_document, ("GET",)),
        ("/workers/<worker_id>/documents/<doc_id>", delete_worker_document, ("DELETE",)),
        ("/leave-requests/<req_id>/export.pdf", export_leave_request_pdf, ("GET",)),
    )
    mount_rules_once("workers", workers_core_bp, rules)


def register_workers_blueprint(flask_app: Flask) -> None:
    from backend.server import (
        ensure_unique_physical_card_id_or_raise,
        get_db,
        get_public_base_url,
        normalize_physical_card_id,
        require_auth,
        require_roles,
        utc_now,
    )

    _register_core_worker_routes()

    @workers_v2_bp.get("/workers")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def v2_list_workers():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        return jsonify({"workers": _service.list_workers_v2(get_db(), cid)})

    @workers_v2_bp.get("/workforce/tracking")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_workforce_tracking():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        today = utc_now().strftime("%Y-%m-%d")
        return jsonify(_service.workforce_tracking(get_db(), cid, today))

    @workers_v2_bp.patch("/workers/<worker_id>/physical-card")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_assign_physical_card(worker_id):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        payload = request.get_json(silent=True) or {}
        physical_card_id = normalize_physical_card_id(payload.get("physicalCardId"))
        try:
            ensure_unique_physical_card_id_or_raise(
                get_db(), physical_card_id, worker_id_to_exclude=worker_id
            )
        except ValueError:
            return jsonify(
                {
                    "error": "duplicate_physical_card_id",
                    "message": "This NFC card is already assigned to another worker.",
                }
            ), 409
        updated = _service.assign_physical_card(get_db(), cid, worker_id, physical_card_id)
        if not updated:
            return jsonify({"error": "worker_not_found"}), 404
        get_db().commit()
        return jsonify({"ok": True, "workerId": worker_id, "physicalCardId": physical_card_id})

    @workers_v2_bp.get("/mobile/distribution")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_mobile_distribution():
        from .mobile_distribution import build_mobile_distribution

        return jsonify(build_mobile_distribution(get_public_base_url()))

    register_blueprint_once(flask_app, workers_core_bp, url_prefix="/api")
    register_blueprint_once(flask_app, workers_v2_bp, url_prefix="/api/v2")
    print("[baupass] domain/workers: all /api/workers/* routes on workers_core_bp", flush=True)
