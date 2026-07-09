"""HTTP routes for live support assist (spectator mode)."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

support_assist_bp = Blueprint("support_assist", __name__)


def register_support_assist_blueprint(flask_app) -> None:
    from backend.server import get_db, require_auth, require_roles

    from .service import append_pulse, end_session, get_active_session, poll_events, start_session

    @support_assist_bp.post("/support-assist/start")
    @require_auth
    @require_roles("superadmin")
    def support_assist_start():
        payload = request.get_json(silent=True) or {}
        company_id = str(payload.get("companyId") or payload.get("company_id") or "").strip()
        actor_name = str(payload.get("actorName") or payload.get("actor_name") or g.current_user.get("name") or "Support").strip()
        if not company_id:
            return jsonify({"error": "missing_company"}), 400
        try:
            result = start_session(get_db(), company_id=company_id, actor_name=actor_name)
            return jsonify({"ok": True, **result})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @support_assist_bp.post("/support-assist/pulse")
    @require_auth
    def support_assist_pulse():
        payload = request.get_json(silent=True) or {}
        company_id = str(payload.get("companyId") or payload.get("company_id") or g.current_user.get("company_id") or "").strip()
        watch_token = str(payload.get("watchToken") or payload.get("watch_token") or "").strip()
        event_type = str(payload.get("type") or "pulse").strip()
        event_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        if not company_id or not watch_token:
            return jsonify({"error": "missing_session"}), 400
        try:
            event = append_pulse(
                company_id=company_id,
                watch_token=watch_token,
                event_type=event_type,
                payload=event_payload,
            )
            return jsonify({"ok": True, "event": event})
        except ValueError as exc:
            code = str(exc)
            status = 403 if code == "invalid_session" else 400
            return jsonify({"error": code}), status

    @support_assist_bp.post("/support-assist/end")
    @require_auth
    def support_assist_end():
        payload = request.get_json(silent=True) or {}
        company_id = str(payload.get("companyId") or payload.get("company_id") or "").strip()
        watch_token = str(payload.get("watchToken") or payload.get("watch_token") or "").strip()
        if company_id and watch_token:
            end_session(company_id=company_id, watch_token=watch_token)
        return jsonify({"ok": True})

    @support_assist_bp.get("/support-assist/active")
    @require_auth
    def support_assist_active():
        company_id = str(request.args.get("company_id") or request.args.get("companyId") or g.current_user.get("company_id") or "").strip()
        if g.current_user.get("role") == "superadmin":
            company_id = str(request.args.get("company_id") or request.args.get("companyId") or company_id).strip()
        if not company_id:
            return jsonify({"active": False})
        row = get_active_session(company_id)
        if not row:
            return jsonify({"active": False})
        if g.current_user.get("role") == "company-admin" and not g.current_user.get("support_read_only"):
            return jsonify(row)
        if g.current_user.get("role") == "superadmin" or g.current_user.get("support_read_only"):
            return jsonify(row)
        return jsonify({"active": False})

    @support_assist_bp.get("/public/support-assist/poll")
    def support_assist_public_poll():
        company_id = str(request.args.get("company_id") or request.args.get("companyId") or "").strip()
        watch_token = str(request.args.get("watch_token") or request.args.get("watchToken") or "").strip()
        since_seq = int(request.args.get("since_seq") or request.args.get("sinceSeq") or 0)
        if not company_id or not watch_token:
            return jsonify({"error": "missing_params"}), 400
        return jsonify(poll_events(company_id=company_id, watch_token=watch_token, since_seq=since_seq))

    @support_assist_bp.get("/public/support-assist/active")
    def support_assist_public_active():
        company_id = str(request.args.get("company_id") or request.args.get("companyId") or "").strip()
        if not company_id:
            return jsonify({"active": False})
        row = get_active_session(company_id)
        if not row:
            return jsonify({"active": False})
        return jsonify(
            {
                "active": True,
                "sessionId": row.get("sessionId"),
                "companyId": row.get("companyId"),
                "actorName": row.get("actorName"),
                "startedAt": row.get("startedAt"),
            }
        )

    flask_app.register_blueprint(support_assist_bp, url_prefix="/api")
    print("[baupass] platform/support_assist: spectator routes registered", flush=True)
