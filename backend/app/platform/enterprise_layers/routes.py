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
    @require_roles("superadmin")
    def siem_export():
        limit = min(500, max(1, int(request.args.get("limit", "100"))))
        rows = get_db().execute(
            """
            SELECT id, event_type, actor_user_id, company_id, message, created_at
            FROM audit_logs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        events = [dict(r) for r in rows]
        return jsonify(
            {
                "format": "baupass_siem_v1",
                "count": len(events),
                "events": events,
            }
        )

    @enterprise_layers_bp.post("/integrations/security-cameras/events")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def security_camera_event():
        from backend.app.platform.physical_operations.camera_ai import ingest_camera_event

        data = request.get_json(silent=True) or {}
        return jsonify(ingest_camera_event(get_db(), _cid(), data))

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
