"""Admin domain — legacy /api/admin/* + v2 dashboard."""
from __future__ import annotations

from flask import Blueprint, Flask, jsonify, request

from .._routes import register_blueprint_once
from ..shared import company_id_from_user, forbidden_company
from .service import AdminService
from .survey_dispatch import (
    check_mail_provider_ready,
    list_invite_candidates,
    send_survey_invites_batch,
)
from .usage_analytics import (
    build_feature_usage_insights,
    build_usage_stats,
    build_usage_trends,
    list_satisfaction_surveys,
    log_feature_usage,
    submit_satisfaction_survey,
    survey_pending_for_user,
)

admin_core_bp = Blueprint("admin_domain_core", __name__)
admin_v2_bp = Blueprint("admin_domain_v2", __name__)
_service = AdminService()


def _register_core_admin_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted, register_blueprint_once

    if routes_already_mounted("admin"):
        return
    from backend.server import (
        admin_create_database_backup,
        admin_download_database_backup,
        admin_gate_devices,
        admin_list_database_backups,
        admin_verify_restore_backup,
        create_device,
        dead_letter_stats,
        delete_device,
        device_health_summary,
        export_device_event_dead_letters_csv,
        get_device_event_dead_letter,
        debug_imap_settings,
        export_audit_csv,
        export_payload,
        get_wallet_runtime_status,
        import_payload,
        list_audit_logs,
        list_device_event_dead_letters,
        list_devices,
        reprocess_device_event_dead_letter,
        resolve_device_event_dead_letter,
    )

    rules = (
        ("/export", export_payload, ("GET",)),
        ("/import", import_payload, ("POST",)),
        ("/debug/imap-settings", debug_imap_settings, ("GET",)),
        ("/audit-logs/export.csv", export_audit_csv, ("GET",)),
        ("/audit-logs", list_audit_logs, ("GET",)),
        ("/admin/wallet/runtime-status", get_wallet_runtime_status, ("GET",)),
        ("/admin/database/backup", admin_create_database_backup, ("POST",)),
        ("/admin/database/backups", admin_list_database_backups, ("GET",)),
        ("/admin/database/backups/verify", admin_verify_restore_backup, ("POST",)),
        ("/admin/database/backups/download", admin_download_database_backup, ("GET",)),
        ("/admin/device-events/dead-letters/stats", dead_letter_stats, ("GET",)),
        ("/admin/device-events/dead-letters/export.csv", export_device_event_dead_letters_csv, ("GET",)),
        ("/admin/device-events/dead-letters", list_device_event_dead_letters, ("GET",)),
        (
            "/admin/device-events/dead-letters/<event_uid>/reprocess",
            reprocess_device_event_dead_letter,
            ("POST",),
        ),
        (
            "/admin/device-events/dead-letters/<event_uid>/resolve",
            resolve_device_event_dead_letter,
            ("POST",),
        ),
        ("/admin/device-events/dead-letters/<event_uid>", get_device_event_dead_letter, ("GET",)),
        ("/admin/devices/health-summary", device_health_summary, ("GET",)),
        ("/admin/devices", list_devices, ("GET",)),
        ("/admin/devices", create_device, ("POST",)),
        ("/admin/devices/<device_id>", delete_device, ("DELETE",)),
        ("/admin/gate-devices", admin_gate_devices, ("GET",)),
    )
    for path, view_func, methods in rules:
        admin_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))
    mark_routes_mounted("admin")


def register_admin_blueprint(flask_app: Flask) -> None:
    from backend.server import get_db, require_auth, require_roles, utc_now

    _register_core_admin_routes()

    @admin_v2_bp.get("/admin/overview")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_admin_overview():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        today = utc_now().strftime("%Y-%m-%d")
        return jsonify(_service.overview(get_db(), cid, today))

    @admin_v2_bp.get("/admin/usage-stats")
    @require_auth
    @require_roles("superadmin")
    def v2_admin_usage_stats():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        period = request.args.get("period") or "day"
        return jsonify(build_usage_stats(get_db(), cid, period=period))

    @admin_v2_bp.get("/admin/usage-trends")
    @require_auth
    @require_roles("superadmin")
    def v2_admin_usage_trends():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        days = int(request.args.get("days") or 14)
        return jsonify(build_usage_trends(get_db(), cid, days=days))

    @admin_v2_bp.get("/admin/feature-usage")
    @require_auth
    @require_roles("superadmin")
    def v2_admin_feature_usage():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        days = int(request.args.get("days") or 14)
        return jsonify(build_feature_usage_insights(get_db(), cid, days=days))

    @admin_v2_bp.get("/admin/satisfaction-surveys")
    @require_auth
    @require_roles("superadmin")
    def v2_admin_satisfaction_surveys():
        cid = company_id_from_user()
        scope = cid if cid else None
        limit = int(request.args.get("limit") or 100)
        return jsonify(list_satisfaction_surveys(get_db(), scope, limit=limit))

    @admin_v2_bp.get("/admin/satisfaction-survey/mail-status")
    @require_auth
    @require_roles("superadmin")
    def v2_admin_survey_mail_status():
        return jsonify(check_mail_provider_ready(get_db()))

    @admin_v2_bp.get("/admin/satisfaction-survey/invite-candidates")
    @require_auth
    @require_roles("superadmin")
    def v2_admin_survey_invite_candidates():
        cid = company_id_from_user()
        return jsonify(list_invite_candidates(get_db(), cid))

    @admin_v2_bp.post("/admin/satisfaction-survey/invite")
    @require_auth
    @require_roles("superadmin")
    def v2_admin_survey_send_invite():
        cid = company_id_from_user()
        data = request.get_json(force=True, silent=True) or {}
        user_id = str(data.get("user_id") or data.get("userId") or "").strip() or None
        send_all = bool(data.get("send_all") or data.get("sendAll"))
        skip_usage = bool(
            data.get("skip_usage_check") or data.get("skipUsageCheck") or send_all
        )
        skip_cooldown = bool(data.get("skip_cooldown") or data.get("skipCooldown"))
        result = send_survey_invites_batch(
            get_db(),
            company_id=cid,
            user_id=user_id,
            send_all=send_all,
            skip_usage_check=skip_usage,
            skip_cooldown=skip_cooldown,
        )
        if result.get("error") == "user_not_found":
            return jsonify(result), 404
        return jsonify(result), 200

    @admin_v2_bp.post("/usage/event")
    @require_auth
    @require_roles("superadmin", "company-admin", "foreman")
    def v2_log_usage_event():
        from flask import g

        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        data = request.get_json(force=True, silent=True) or {}
        feature_id = str(data.get("feature_id") or data.get("featureId") or "").strip()
        if not feature_id:
            return jsonify({"error": "feature_id_required"}), 400
        user = getattr(g, "current_user", {}) or {}
        log_feature_usage(
            get_db(),
            cid,
            str(user.get("id") or ""),
            feature_id,
            source=str(data.get("source") or "admin-v2")[:32],
        )
        return jsonify({"ok": True})

    @admin_v2_bp.get("/satisfaction-survey/pending")
    @require_auth
    @require_roles("superadmin", "company-admin", "foreman")
    def v2_satisfaction_survey_pending():
        from flask import g

        user = getattr(g, "current_user", {}) or {}
        return jsonify(survey_pending_for_user(get_db(), user))

    @admin_v2_bp.post("/satisfaction-survey")
    @require_auth
    @require_roles("superadmin", "company-admin", "foreman")
    def v2_satisfaction_survey_submit():
        from flask import g

        user = dict(getattr(g, "current_user", {}) or {})
        cid = company_id_from_user()
        if cid and not user.get("company_id"):
            user["company_id"] = cid
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = submit_satisfaction_survey(get_db(), user, data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result)

    register_blueprint_once(flask_app, admin_core_bp, url_prefix="/api")
    register_blueprint_once(flask_app, admin_v2_bp, url_prefix="/api/v2")
    print("[baupass] domain/admin: all /api/admin/* routes on admin_core_bp", flush=True)
