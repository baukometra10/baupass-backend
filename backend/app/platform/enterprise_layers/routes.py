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
        if g.current_user.get("role") == "superadmin":
            raw = str(request.args.get("company_id", "") or "").strip()
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
                scope_company_id = str(request.headers.get("X-BauPass-Company-Id") or request.args.get("company_id") or "").strip() or scope_company_id

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
            return jsonify({"error": "company_id_required"}), 400
        limit = min(100, max(1, int(request.args.get("limit", "30"))))
        rows = get_db().execute(
            """
            SELECT id, camera_id, event_type, worker_id, confidence, ppe_compliant, zone_violation, created_at
            FROM camera_ai_events
            WHERE company_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (cid, limit),
        ).fetchall()
        return jsonify({"events": [dict(r) for r in rows]})

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
