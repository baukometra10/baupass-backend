"""
Six enterprise layers — unified API surface.
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, g, jsonify, request

enterprise_layers_bp = Blueprint("enterprise_layers", __name__)


def register_enterprise_layers(flask_app) -> None:
    from backend.server import require_auth, require_roles, get_db, DB_PATH

    def _cid() -> str:
        body = request.get_json(silent=True) if request.method in {"POST", "PUT", "PATCH"} else None
        body = body if isinstance(body, dict) else {}
        # Prefer explicit company scope (query, header, body) — required for superadmin preview.
        raw = str(
            request.args.get("company_id", "")
            or request.headers.get("X-WorkPass-Company-Id")
            or request.headers.get("X-SUPPIX-Company-Id")
            or body.get("companyId")
            or body.get("company_id")
            or ""
        ).strip()
        if raw:
            return raw
        return str(g.current_user.get("company_id") or "").strip()

    @enterprise_layers_bp.get("/enterprise/layers")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def all_layers():
        from .intelligence_hub import build_intelligence_layer
        from .integration_ecosystem import build_integration_ecosystem
        from .platform_ecosystem import build_platform_ecosystem_layer
        from .infrastructure_layer import build_infrastructure_layer
        from .security_compliance import build_security_compliance_layer
        from .operational_experience import build_operational_experience_layer

        cid = _cid()
        db = get_db()
        return jsonify(
            {
                "layers": {
                    "intelligence": build_intelligence_layer(db, cid),
                    "integrations": build_integration_ecosystem(db, cid),
                    "platform": build_platform_ecosystem_layer(),
                    "infrastructure": build_infrastructure_layer(Path(DB_PATH)),
                    "security_compliance": build_security_compliance_layer(db),
                    "operational_experience": build_operational_experience_layer(),
                }
            }
        )

    @enterprise_layers_bp.get("/enterprise/layers/<layer_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def single_layer(layer_id: str):
        cid = _cid()
        db = get_db()
        lid = layer_id.strip().lower()
        if lid in {"intelligence", "1"}:
            from .intelligence_hub import build_intelligence_layer

            return jsonify(build_intelligence_layer(db, cid))
        if lid in {"integrations", "integration", "2"}:
            from .integration_ecosystem import build_integration_ecosystem

            return jsonify(build_integration_ecosystem(db, cid))
        if lid in {"platform", "ecosystem", "3"}:
            from .platform_ecosystem import build_platform_ecosystem_layer

            return jsonify(build_platform_ecosystem_layer())
        if lid in {"infrastructure", "hyper-scale", "4"}:
            from .infrastructure_layer import build_infrastructure_layer

            return jsonify(build_infrastructure_layer(Path(DB_PATH)))
        if lid in {"security", "compliance", "5"}:
            from .security_compliance import build_security_compliance_layer

            return jsonify(build_security_compliance_layer(db))
        if lid in {"experience", "ux", "operational", "6"}:
            from .operational_experience import build_operational_experience_layer

            return jsonify(build_operational_experience_layer())
        return jsonify({"error": "unknown_layer", "valid": ["intelligence", "integrations", "platform", "infrastructure", "security", "experience"]}), 404

    @enterprise_layers_bp.get("/enterprise/security/siem-export")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def siem_export():
        from backend.app.platform.enterprise_layers.siem_export import export_siem_payload
        from backend.app.platform.rbac.enforcement import has_permission

        user = g.current_user
        db = get_db()
        if user.get("role") != "superadmin" and not has_permission(db, user, "security.export"):
            if not has_permission(db, user, "audit.read"):
                return jsonify({"error": "forbidden"}), 403

        company_id = None
        if user.get("role") != "superadmin":
            company_id = str(user.get("company_id") or "")
        elif request.args.get("company_id"):
            company_id = str(request.args.get("company_id")).strip()

        limit = int(request.args.get("limit", "200"))
        source = str(request.args.get("source", "both")).strip().lower()
        fmt = str(request.args.get("format", "json")).strip().lower()
        payload = export_siem_payload(db, company_id=company_id, limit=limit, source=source, fmt=fmt)
        if fmt == "cef":
            return "\n".join(payload.get("lines") or []), 200, {"Content-Type": "text/plain; charset=utf-8"}
        return jsonify(payload)

    @enterprise_layers_bp.get("/enterprise/security/audit-chain/verify")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def verify_audit_chain():
        from backend.app.audit.immutable import verify_immutable_audit_chain
        from backend.app.platform.rbac.enforcement import has_permission

        if g.current_user.get("role") != "superadmin" and not has_permission(
            get_db(), g.current_user, "audit.read"
        ):
            return jsonify({"error": "forbidden"}), 403
        limit = request.args.get("limit")
        lim = int(limit) if limit else None
        result = verify_immutable_audit_chain(get_db(), limit=lim)
        return jsonify(result)

    @enterprise_layers_bp.post("/integrations/security-cameras/events")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def security_camera_event():
        from backend.app.platform.physical_operations.camera_ai import ingest_camera_event

        data = request.get_json(silent=True) or {}
        return jsonify(ingest_camera_event(get_db(), _cid(), data))

    @enterprise_layers_bp.post("/integrations/cameras/rtsp-ingest")
    def camera_rtsp_ingest():
        """RTSP/NVR local bridge — token, device key, or admin session."""
        from backend.app.platform.physical_operations.rtsp_bridge import (
            authorize_rtsp_bridge_request,
            ingest_rtsp_camera_event,
        )

        db = get_db()
        actor, scope_company_id, err_code = authorize_rtsp_bridge_request(request, db)
        if err_code:
            from backend.server import get_auth_token_from_request, row_to_dict

            token = get_auth_token_from_request()
            if not token:
                return jsonify({"error": "unauthorized"}), 401
            session = db.execute("SELECT user_id FROM sessions WHERE token = ?", (token,)).fetchone()
            if not session:
                return jsonify({"error": "unauthorized"}), 401
            user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
            if not user or str(user["role"] or "") not in {"superadmin", "company-admin", "turnstile"}:
                return jsonify({"error": "unauthorized"}), 401
            actor = row_to_dict(user)
            scope_company_id = str(actor.get("company_id") or "").strip() or None
            if actor.get("role") == "superadmin":
                scope_company_id = str(request.headers.get("X-SUPPIX-Company-Id") or request.args.get("company_id") or "").strip() or scope_company_id

        payload = request.get_json(silent=True) or {}
        company_id = str(payload.get("companyId") or payload.get("company_id") or scope_company_id or _cid() or "").strip()
        if not company_id:
            return jsonify({"error": "missing_company_id"}), 400
        if scope_company_id and str(company_id) != str(scope_company_id):
            return jsonify({"error": "forbidden_company"}), 403

        result = ingest_rtsp_camera_event(db, company_id, payload)
        if not result.get("ok", True):
            return jsonify(result), 400
        return jsonify(result)

    @enterprise_layers_bp.get("/integrations/cameras/events")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def list_camera_events():
        cid = _cid()
        if not cid:
            return jsonify({"events": [], "hint": "company_id_required"})
        limit = min(100, max(1, int(request.args.get("limit", "30"))))
        rows = get_db().execute(
            """
            SELECT id, camera_id, event_type, worker_id, confidence, ppe_compliant,
                   zone_violation, payload_json, created_at
            FROM camera_ai_events
            WHERE company_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (cid, limit),
        ).fetchall()
        return jsonify({"events": [dict(r) for r in rows]})

    @enterprise_layers_bp.get("/integrations/cameras")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def list_site_cameras():
        from backend.app.platform.physical_operations.camera_registry import list_cameras
        import traceback
        import logging

        cid = _cid()
        if not cid:
            return jsonify({"cameras": [], "hint": "company_id_required"})
        
        try:
            db = get_db()
            cameras = list_cameras(db, cid)
            online = sum(1 for c in cameras if c.get("online"))
            watch = {}
            try:
                from backend.app.platform.physical_operations.camera_watch import watch_status

                watch = watch_status(db, cid)
            except Exception:
                watch = {}
            return jsonify(
                {
                    "cameras": cameras,
                    "summary": {
                        "total": len(cameras),
                        "online": online,
                        "offline": len(cameras) - online,
                        "watchModeActive": bool(watch.get("watchModeActive")),
                        "afterHours": bool(watch.get("afterHours")),
                        "watchEnabled": bool(watch.get("enabled", True)),
                    },
                    "watch": watch,
                }
            )
        except Exception as e:
            error_msg = str(e)
            if "no such table" in error_msg.lower() or "does not exist" in error_msg.lower():
                return jsonify({"cameras": [], "summary": {"total": 0, "online": 0, "offline": 0}, "hint": "migration_pending"})
            logging.error(f"Failed to list cameras for company {cid}: {error_msg}\n{traceback.format_exc()}")
            return jsonify({"error": "database_error", "detail": error_msg}), 500

    @enterprise_layers_bp.post("/integrations/cameras")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def create_site_camera():
        from backend.app.platform.physical_operations.camera_registry import create_camera

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        data = request.get_json(silent=True) or {}
        try:
            cam = create_camera(get_db(), cid, data)
            return jsonify({"ok": True, "camera": cam}), 201
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @enterprise_layers_bp.post("/integrations/cameras/bulk")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def bulk_create_site_cameras():
        from backend.app.platform.physical_operations.camera_registry import (
            bulk_create_cameras,
            parse_camera_bulk_text,
        )

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        data = request.get_json(silent=True) or {}
        items: list = []
        if isinstance(data.get("cameras"), list):
            items = data["cameras"]
        elif isinstance(data.get("lines"), str):
            items = parse_camera_bulk_text(data["lines"])
        elif isinstance(data.get("text"), str):
            items = parse_camera_bulk_text(data["text"])
        if not items:
            return jsonify({"error": "no_cameras", "message": "Provide cameras[] or lines text"}), 400
        if len(items) > 100:
            return jsonify({"error": "too_many", "message": "Max 100 cameras per batch"}), 400
        result = bulk_create_cameras(get_db(), cid, items)
        if result.get("created"):
            return jsonify(result), 201
        return jsonify(result), 400

    @enterprise_layers_bp.get("/integrations/cameras/setup")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def camera_setup_info():
        import os

        from backend.app.platform.physical_operations.camera_registry import list_cameras

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        token = (
            os.getenv("BAUPASS_RTSP_BRIDGE_TOKEN", "").strip()
            or os.getenv("SUPPIX_RTSP_BRIDGE_TOKEN", "").strip()
        )
        try:
            from backend.server import get_public_base_url

            api_url = get_public_base_url()
        except Exception:
            api_url = request.url_root.rstrip("/")
        cameras = list_cameras(get_db(), cid)
        with_rtsp = [c for c in cameras if str(c.get("rtspUrl") or "").strip()]
        return jsonify(
            {
                "ok": True,
                "companyId": cid,
                "apiUrl": api_url,
                "ingestPath": "/api/integrations/cameras/rtsp-ingest",
                "rtspBridgeConfigured": bool(token),
                "cameraCount": len(cameras),
                "camerasWithRtsp": len(with_rtsp),
                "headers": {
                    "rtspToken": "X-WorkPass-Rtsp-Token",
                    "companyId": "X-WorkPass-Company-Id",
                },
                "agent": {
                    "script": "scripts/rtsp_camera_agent.py",
                    "env": {
                        "BAUPASS_API_URL": api_url,
                        "BAUPASS_COMPANY_ID": cid,
                        "BAUPASS_RTSP_BRIDGE_TOKEN": "<set-on-server>",
                    },
                    "multiCameraFlag": "--cameras-file",
                },
            }
        )

    @enterprise_layers_bp.put("/integrations/cameras/<camera_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def update_site_camera(camera_id):
        from backend.app.platform.physical_operations.camera_registry import update_camera

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        data = request.get_json(silent=True) or {}
        cam = update_camera(get_db(), cid, camera_id, data)
        if not cam:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True, "camera": cam})

    @enterprise_layers_bp.delete("/integrations/cameras/<camera_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def delete_site_camera(camera_id):
        from backend.app.platform.physical_operations.camera_registry import delete_camera

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        if not delete_camera(get_db(), cid, camera_id):
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True})

    @enterprise_layers_bp.get("/integrations/cameras/<camera_id>/snapshot")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def camera_live_snapshot(camera_id):
        import base64

        from flask import Response

        from backend.app.platform.physical_operations.camera_registry import get_camera_snapshot_b64

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        fmt = str(request.args.get("format", "json") or "json").lower()
        b64 = get_camera_snapshot_b64(get_db(), cid, camera_id)
        if not b64:
            return jsonify({"error": "no_snapshot", "cameraId": camera_id}), 404
        if fmt == "jpeg" or fmt == "jpg":
            try:
                data = base64.b64decode(b64)
                resp = Response(data, mimetype="image/jpeg")
                resp.headers["Cache-Control"] = "no-store, max-age=0"
                return resp
            except Exception:
                return jsonify({"error": "invalid_snapshot"}), 500
        return jsonify({"cameraId": camera_id, "snapshotBase64": b64})

    @enterprise_layers_bp.get("/integrations/cameras/watch")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def get_camera_watch():
        from backend.app.platform.physical_operations.camera_escalation import list_escalations
        from backend.app.platform.physical_operations.camera_watch import (
            list_watch_overrides,
            list_watch_sites,
            watch_status,
        )

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        db = get_db()
        errors: list[str] = []
        try:
            status = watch_status(db, cid)
        except Exception as exc:
            errors.append(f"watch:{exc}")
            status = {
                "companyId": cid,
                "enabled": True,
                "afterHours": False,
                "watchModeActive": False,
                "label": "watch_standby",
                "error": str(exc),
            }
        try:
            sites = list_watch_sites(db, cid)
        except Exception as exc:
            errors.append(f"sites:{exc}")
            sites = []
        try:
            overrides = list_watch_overrides(db, cid)
        except Exception as exc:
            errors.append(f"overrides:{exc}")
            overrides = []
        try:
            escalations = list_escalations(db, cid, limit=20)
        except Exception as exc:
            errors.append(f"escalations:{exc}")
            escalations = []
        return jsonify(
            {
                "ok": True,
                "watch": status,
                "notifyRules": (status or {}).get("notifyRules") or {},
                "sites": sites,
                "overrides": overrides,
                "escalations": escalations,
                "warnings": errors,
                "autoDial": False,
            }
        )

    @enterprise_layers_bp.put("/integrations/cameras/watch")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def put_camera_watch():
        from backend.app.platform.physical_operations.camera_watch import (
            list_watch_sites,
            upsert_watch_settings,
            watch_status,
        )

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        data = request.get_json(silent=True) or {}
        try:
            upsert_watch_settings(get_db(), cid, data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        db = get_db()
        return jsonify({"ok": True, "watch": watch_status(db, cid), "sites": list_watch_sites(db, cid)})

    @enterprise_layers_bp.put("/integrations/cameras/watch/sites/<site_key>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def put_camera_watch_site(site_key: str):
        from backend.app.platform.physical_operations.camera_watch import upsert_site_watch_settings

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        data = request.get_json(silent=True) or {}
        try:
            site = upsert_site_watch_settings(get_db(), cid, site_key, data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "site": site})

    @enterprise_layers_bp.delete("/integrations/cameras/watch/sites/<site_key>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def delete_camera_watch_site(site_key: str):
        from backend.app.platform.physical_operations.camera_watch import delete_site_watch_settings

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        ok = delete_site_watch_settings(get_db(), cid, site_key)
        if not ok:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True})

    @enterprise_layers_bp.get("/integrations/cameras/watch/overrides")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def list_camera_watch_overrides():
        from backend.app.platform.physical_operations.camera_watch import list_watch_overrides

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        return jsonify({"ok": True, "overrides": list_watch_overrides(get_db(), cid)})

    @enterprise_layers_bp.put("/integrations/cameras/watch/overrides")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def put_camera_watch_override():
        from backend.app.platform.physical_operations.camera_watch import upsert_watch_override

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        data = request.get_json(silent=True) or {}
        try:
            item = upsert_watch_override(get_db(), cid, data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "override": item})

    @enterprise_layers_bp.delete("/integrations/cameras/watch/overrides")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def delete_camera_watch_override():
        from backend.app.platform.physical_operations.camera_watch import delete_watch_override

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        data = request.get_json(silent=True) or {}
        override_date = str(
            request.args.get("overrideDate")
            or request.args.get("override_date")
            or data.get("overrideDate")
            or data.get("override_date")
            or ""
        ).strip()
        site_key = str(
            request.args.get("siteKey")
            or request.args.get("site_key")
            or data.get("siteKey")
            or data.get("site_key")
            or ""
        )
        if not override_date:
            return jsonify({"error": "override_date_required"}), 400
        ok = delete_watch_override(get_db(), cid, override_date, site_key=site_key)
        if not ok:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True})

    @enterprise_layers_bp.post("/integrations/cameras/watch/test-alarm")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def post_camera_watch_test_alarm():
        from backend.app.platform.physical_operations.camera_escalation import create_test_alarm

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        data = request.get_json(silent=True) or {}
        try:
            result = create_test_alarm(
                get_db(),
                cid,
                dry_run=bool(data.get("dryRun") or data.get("dry_run")),
                severity=str(data.get("severity") or "high"),
                send_webhook=bool(data.get("sendWebhook", data.get("send_webhook", True))),
                actor_user_id=str(g.current_user.get("id") or g.current_user.get("username") or ""),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc), "autoDial": False}), 400
        return jsonify({**result, "autoDial": False})

    @enterprise_layers_bp.post("/integrations/cameras/watch/test-webhook")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def post_camera_watch_test_webhook():
        from backend.app.platform.physical_operations.camera_webhook import fire_test_webhook
        from backend.app.platform.physical_operations.camera_watch import resolve_watch_settings

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        data = request.get_json(silent=True) or {}
        cfg = resolve_watch_settings(get_db(), cid)
        result = fire_test_webhook(
            get_db(),
            cid,
            url=str(data.get("url") or data.get("securityWebhookUrl") or "") or None,
            secret=data.get("secret") if "secret" in data or "webhookSecret" in data else None,
            watch_cfg={
                **cfg,
                "securityWebhookUrl": str(
                    data.get("url") or data.get("securityWebhookUrl") or cfg.get("securityWebhookUrl") or ""
                ),
                "webhookSecret": str(
                    data.get("secret")
                    if "secret" in data
                    else data.get("webhookSecret", cfg.get("webhookSecret") or "")
                ),
            },
        )
        # Missing URL is a client config issue — return 200 with ok:false for UI messaging.
        if result.get("error") == "webhook_url_required":
            return jsonify(
                {
                    **result,
                    "message": "Bitte zuerst Security-Webhook (Firma) speichern (https://…), dann testen.",
                }
            ), 200
        status = 200 if result.get("ok") else 400
        return jsonify(result), status

    @enterprise_layers_bp.get("/integrations/cameras/watch/audit-export")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def get_camera_watch_audit_export():
        from flask import Response

        from backend.app.platform.physical_operations.camera_export import build_audit_export

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        fmt = str(request.args.get("format") or "json").strip().lower()
        try:
            data, mime, filename = build_audit_export(
                get_db(),
                cid,
                from_ts=request.args.get("from") or request.args.get("from_ts"),
                to_ts=request.args.get("to") or request.args.get("to_ts"),
                fmt=fmt,
                include_media=str(request.args.get("media") or "0").lower() in {"1", "true", "yes"},
            )
        except Exception as exc:
            return jsonify({"error": str(exc), "autoDial": False}), 500
        return Response(
            data,
            mimetype=mime,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @enterprise_layers_bp.get("/integrations/cameras/escalations")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def list_camera_escalations():
        from backend.app.platform.physical_operations.camera_escalation import list_escalations

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        status = request.args.get("status")
        limit = min(100, max(1, int(request.args.get("limit", "30"))))
        return jsonify({"ok": True, "items": list_escalations(get_db(), cid, limit=limit, status=status)})

    @enterprise_layers_bp.get("/integrations/cameras/escalations/<escalation_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def get_camera_escalation(escalation_id: str):
        from backend.app.platform.physical_operations.camera_escalation import get_escalation

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        include_media = str(request.args.get("media") or "1").lower() not in {"0", "false", "no"}
        item = get_escalation(get_db(), cid, escalation_id, include_media=include_media)
        if not item:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True, "escalation": item})

    @enterprise_layers_bp.post("/integrations/cameras/escalations/<escalation_id>/ack")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ack_camera_escalation(escalation_id: str):
        from backend.app.platform.physical_operations.camera_escalation import acknowledge_escalation

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        data = request.get_json(silent=True) or {}
        try:
            item = acknowledge_escalation(
                get_db(),
                cid,
                escalation_id,
                actor_user_id=str(g.current_user.get("id") or g.current_user.get("username") or ""),
                mark_security_notified=bool(data.get("securityNotified") or data.get("notifySecurity")),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not item:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True, "escalation": item})

    @enterprise_layers_bp.post("/integrations/cameras/escalations/<escalation_id>/false-positive")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def false_positive_camera_escalation(escalation_id: str):
        from backend.app.platform.physical_operations.camera_escalation import mark_false_positive

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        data = request.get_json(silent=True) or {}
        item = mark_false_positive(
            get_db(),
            cid,
            escalation_id,
            actor_user_id=str(g.current_user.get("id") or g.current_user.get("username") or ""),
            note=str(data.get("note") or ""),
        )
        if not item:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True, "escalation": item})

    @enterprise_layers_bp.get("/integrations/cameras/escalations/<escalation_id>/export")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def export_camera_escalation(escalation_id: str):
        from flask import Response

        from backend.app.platform.physical_operations.camera_export import (
            build_escalation_export_pdf,
            build_escalation_export_zip,
        )

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        fmt = str(request.args.get("format") or "zip").strip().lower()
        try:
            if fmt == "pdf":
                data = build_escalation_export_pdf(get_db(), cid, escalation_id)
                return Response(
                    data,
                    mimetype="application/pdf",
                    headers={
                        "Content-Disposition": f'attachment; filename="escalation-{escalation_id}.pdf"'
                    },
                )
            data = build_escalation_export_zip(get_db(), cid, escalation_id)
            return Response(
                data,
                mimetype="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="escalation-{escalation_id}.zip"'
                },
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @enterprise_layers_bp.post("/integrations/cameras/nvr/<vendor>")
    def camera_nvr_webhook(vendor: str):
        """NVR vendor webhook — token, device key, or admin session."""
        from backend.app.platform.physical_operations.nvr_webhook import ingest_nvr_webhook
        from backend.app.platform.physical_operations.rtsp_bridge import authorize_rtsp_bridge_request

        db = get_db()
        actor, scope_company_id, err_code = authorize_rtsp_bridge_request(request, db)
        if err_code:
            from backend.server import get_auth_token_from_request, row_to_dict

            token = get_auth_token_from_request()
            if not token:
                return jsonify({"error": "unauthorized"}), 401
            session = db.execute("SELECT user_id FROM sessions WHERE token = ?", (token,)).fetchone()
            if not session:
                return jsonify({"error": "unauthorized"}), 401
            user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
            if not user or str(user["role"] or "") not in {"superadmin", "company-admin", "turnstile"}:
                return jsonify({"error": "unauthorized"}), 401
            actor = row_to_dict(user)
            scope_company_id = str(actor.get("company_id") or "").strip() or None
            if actor.get("role") == "superadmin":
                scope_company_id = (
                    str(
                        request.headers.get("X-SUPPIX-Company-Id")
                        or request.args.get("company_id")
                        or ""
                    ).strip()
                    or scope_company_id
                )

        payload = request.get_json(silent=True) or {}
        company_id = str(
            payload.get("companyId") or payload.get("company_id") or scope_company_id or _cid() or ""
        ).strip()
        if not company_id:
            return jsonify({"error": "missing_company_id"}), 400
        if scope_company_id and str(company_id) != str(scope_company_id):
            return jsonify({"error": "forbidden_company"}), 403

        headers = {k: v for k, v in request.headers.items()}
        result = ingest_nvr_webhook(db, company_id, vendor, payload, headers)
        if not result.get("ok", True):
            return jsonify(result), 400
        return jsonify(result)

    @enterprise_layers_bp.post("/integrations/biometric/events")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def biometric_event():
        from backend.app.platform.events.bus import publish_event

        data = request.get_json(silent=True) or {}
        publish_event(
            "integration.biometric.event",
            _cid(),
            {"reader_id": data.get("reader_id"), "worker_id": data.get("worker_id"), "payload": data},
        )
        return jsonify({"ok": True})

    flask_app.register_blueprint(enterprise_layers_bp, url_prefix="/api")
