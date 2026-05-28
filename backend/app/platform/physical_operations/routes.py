"""
Physical Operations OS — all 12 capabilities under /api/ops-os/*
"""
from __future__ import annotations

import uuid

from flask import Blueprint, Response, g, jsonify, request

ops_os_bp = Blueprint("physical_operations", __name__)


def register_physical_operations(flask_app) -> None:
    from backend.server import require_auth, require_roles, get_db, log_audit

    from ._common import company_id_from_user, now_iso
    from .digital_twin import build_digital_twin
    from .site_intelligence import build_site_intelligence
    from .security_engine import analyze_security
    from .reputation import build_reputation_leaderboard, compute_worker_reputation
    from .emergency import build_emergency_status, mark_roll_call, start_roll_call, get_emergency
    from .camera_ai import ingest_camera_event
    from .iot_registry import build_iot_overview, list_devices, register_device, record_telemetry
    from .command_center import build_command_center
    from .workforce_graph import build_workforce_graph
    from .identity_hub import build_identity_hub
    from .copilot import copilot_query, build_copilot_context

    def _cid() -> str:
        cid = company_id_from_user(g.current_user, request.args)
        if cid:
            return cid
        if g.current_user.get("role") == "superadmin":
            return str(request.args.get("company_id", "") or "").strip()
        return str(g.current_user.get("company_id") or "").strip()

    # ── Overview (all 12 layers) ──────────────────────────────────────────────
    @ops_os_bp.get("/ops-os/overview")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_overview():
        cid = _cid()
        if not cid and g.current_user.get("role") != "superadmin":
            return jsonify({"error": "company_required"}), 400
        db = get_db()
        role = g.current_user.get("role", "")
        cid = cid or str(request.args.get("company_id", "") or "").strip()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        return jsonify(
            {
                "physicalOperationsOS": True,
                "companyId": cid,
                "layers": {
                    "1_digital_twin": build_digital_twin(db, cid),
                    "2_ai_security": analyze_security(db, cid, persist=False),
                    "3_site_intelligence": build_site_intelligence(db, cid),
                    "4_reputation": build_reputation_leaderboard(db, cid, limit=50),
                    "5_emergency": _active_emergency_summary(db, cid),
                    "6_camera_ai": _camera_summary(db, cid),
                    "7_iot": build_iot_overview(db, cid),
                    "8_command_center": build_command_center(db, company_id=cid, role=role),
                    "9_autonomous": _autonomous_summary(db, cid),
                    "10_workforce_graph": build_workforce_graph(db, cid),
                    "11_identity": build_identity_hub(db, cid),
                    "12_copilot": {"configured": True, "endpoint": "POST /api/ops-os/copilot"},
                },
            }
        )

    def _active_emergency_summary(db, cid):
        row = db.execute(
            "SELECT id FROM emergency_events WHERE company_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (cid,),
        ).fetchone()
        if not row:
            return {"active": False}
        return {"active": True, **build_emergency_status(db, row["id"], cid)}

    def _camera_summary(db, cid):
        try:
            c = db.execute(
                "SELECT COUNT(*) AS c FROM camera_ai_events WHERE company_id = ? AND created_at >= datetime('now', '-24 hours')",
                (cid,),
            ).fetchone()
            return {"events24h": int(c["c"] or 0)}
        except Exception:
            return {"events24h": 0}

    def _autonomous_summary(db, cid):
        rows = db.execute(
            "SELECT COUNT(*) AS c FROM automation_rules WHERE company_id = ? AND enabled = 1",
            (cid,),
        ).fetchone()
        return {"enabledRules": int((rows["c"] if rows else 0) or 0), "api": "/api/automation/rules"}

    @ops_os_bp.get("/ops-os/digital-twin")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def digital_twin():
        cid = _cid()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        return jsonify(build_digital_twin(get_db(), cid))

    @ops_os_bp.get("/ops-os/site-intelligence")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def site_intelligence():
        cid = _cid()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        return jsonify(build_site_intelligence(get_db(), cid))

    @ops_os_bp.get("/ops-os/security-engine")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def security_engine():
        cid = _cid()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        persist = request.args.get("persist", "1") not in {"0", "false"}
        return jsonify(analyze_security(get_db(), cid, persist=persist))

    @ops_os_bp.get("/ops-os/reputation")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def reputation_board():
        cid = _cid()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        limit = min(500, max(1, int(request.args.get("limit", "100"))))
        return jsonify(build_reputation_leaderboard(get_db(), cid, limit=limit))

    @ops_os_bp.get("/ops-os/reputation/<worker_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def reputation_worker(worker_id: str):
        cid = _cid()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        return jsonify(compute_worker_reputation(get_db(), cid, worker_id))

    @ops_os_bp.post("/ops-os/emergency")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def emergency_create():
        data = request.get_json(silent=True) or {}
        cid = _cid()
        eid = f"emg-{uuid.uuid4().hex[:10]}"
        msg = str(data.get("message", "Emergency")).strip()
        etype = str(data.get("emergency_type", data.get("type", "evacuation"))).strip()
        site = str(data.get("site_name", data.get("site", ""))).strip()
        db = get_db()
        try:
            db.execute(
                """
                INSERT INTO emergency_events
                    (id, company_id, message, status, created_by, created_at, emergency_type, site_name)
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (eid, cid, msg, str(g.current_user.get("id", "")), now_iso(), etype, site),
            )
        except Exception:
            db.execute(
                """
                INSERT INTO emergency_events (id, company_id, message, status, created_by, created_at)
                VALUES (?, ?, ?, 'active', ?, ?)
                """,
                (eid, cid, msg, str(g.current_user.get("id", "")), now_iso()),
            )
        db.commit()
        from backend.app.platform.events.bus import publish_event

        publish_event("emergency.triggered", cid, {"emergency_id": eid, "type": etype})
        log_audit("emergency.triggered", msg, company_id=cid, actor=g.current_user)
        start_roll_call(db, eid, cid, marked_by=str(g.current_user.get("id", "")))
        return jsonify(build_emergency_status(db, eid, cid)), 201

    @ops_os_bp.get("/ops-os/emergency/<emergency_id>")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def emergency_status(emergency_id: str):
        cid = _cid()
        return jsonify(build_emergency_status(get_db(), emergency_id, cid))

    @ops_os_bp.post("/ops-os/emergency/<emergency_id>/roll-call")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def emergency_roll_call_refresh(emergency_id: str):
        cid = _cid()
        return jsonify(start_roll_call(get_db(), emergency_id, cid, marked_by=str(g.current_user.get("id", ""))))

    @ops_os_bp.put("/ops-os/emergency/<emergency_id>/workers/<worker_id>")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def emergency_mark_worker(emergency_id: str, worker_id: str):
        data = request.get_json(silent=True) or {}
        status = str(data.get("status", "safe")).strip()
        cid = _cid()
        return jsonify(
            mark_roll_call(
                get_db(),
                emergency_id,
                cid,
                worker_id,
                status,
                marked_by=str(g.current_user.get("id", "")),
            )
        )

    @ops_os_bp.post("/ops-os/emergency/<emergency_id>/resolve")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def emergency_resolve(emergency_id: str):
        cid = _cid()
        db = get_db()
        if not get_emergency(db, emergency_id, cid):
            return jsonify({"error": "emergency_not_found"}), 404
        db.execute(
            "UPDATE emergency_events SET status = 'resolved', resolved_at = ? WHERE id = ?",
            (now_iso(), emergency_id),
        )
        db.commit()
        return jsonify({"id": emergency_id, "status": "resolved"})

    @ops_os_bp.post("/ops-os/cameras/analyze")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def camera_analyze():
        cid = _cid()
        data = request.get_json(silent=True) or {}
        return jsonify(ingest_camera_event(get_db(), cid, data))

    @ops_os_bp.get("/ops-os/cameras/events")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def camera_events():
        cid = _cid()
        limit = min(200, max(1, int(request.args.get("limit", "50"))))
        try:
            rows = get_db().execute(
                """
                SELECT * FROM camera_ai_events WHERE company_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (cid, limit),
            ).fetchall()
            return jsonify({"events": [dict(r) for r in rows]})
        except Exception:
            return jsonify({"events": []})

    @ops_os_bp.get("/ops-os/iot")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def iot_overview():
        cid = _cid()
        return jsonify(build_iot_overview(get_db(), cid))

    @ops_os_bp.get("/ops-os/iot/devices")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def iot_devices_list():
        return jsonify({"devices": list_devices(get_db(), _cid())})

    @ops_os_bp.post("/ops-os/iot/devices")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def iot_devices_register():
        data = request.get_json(silent=True) or {}
        return jsonify(register_device(get_db(), _cid(), data)), 201

    @ops_os_bp.post("/ops-os/iot/devices/<device_id>/telemetry")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def iot_telemetry(device_id: str):
        data = request.get_json(silent=True) or {}
        return jsonify(record_telemetry(get_db(), device_id, _cid(), data))

    @ops_os_bp.get("/ops-os/command-center")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def command_center():
        role = g.current_user.get("role", "")
        cid = _cid() if role != "superadmin" or request.args.get("company_id") else None
        if role == "superadmin" and request.args.get("company_id"):
            cid = str(request.args.get("company_id", "") or "").strip()
        return jsonify(build_command_center(get_db(), company_id=cid, role=role))

    @ops_os_bp.get("/ops-os/events/stream")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_events_stream():
        from backend.app.platform.ops_events import stream_ops_events

        role = g.current_user.get("role", "")
        cid = _cid() if role != "superadmin" or request.args.get("company_id") else None
        if role == "superadmin" and request.args.get("company_id"):
            cid = str(request.args.get("company_id", "") or "").strip() or None
        return Response(
            stream_ops_events(get_db(), cid or None),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @ops_os_bp.get("/ops-os/workforce-graph")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def workforce_graph():
        cid = _cid()
        days = int(request.args.get("days", "14"))
        return jsonify(build_workforce_graph(get_db(), cid, days=days))

    @ops_os_bp.get("/ops-os/identity")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def identity():
        cid = _cid()
        wid = request.args.get("worker_id", "").strip() or None
        return jsonify(build_identity_hub(get_db(), cid, wid))

    @ops_os_bp.post("/ops-os/copilot")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def copilot():
        data = request.get_json(silent=True) or {}
        question = str(data.get("question", "")).strip()
        if not question:
            return jsonify({"error": "question_required"}), 400
        cid = _cid()
        if g.current_user.get("role") == "superadmin" and data.get("company_id"):
            cid = str(data.get("company_id", "") or "").strip()
        return jsonify(copilot_query(get_db(), cid, question, g.current_user.get("role", "")))

    @ops_os_bp.get("/ops-os/copilot/context")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def copilot_context():
        cid = _cid()
        return jsonify(build_copilot_context(get_db(), cid, g.current_user.get("role", "")))

    # ── Site assets CRUD ──────────────────────────────────────────────────────
    @ops_os_bp.get("/ops-os/equipment")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def list_equipment():
        cid = _cid()
        try:
            rows = get_db().execute("SELECT * FROM site_equipment WHERE company_id = ?", (cid,)).fetchall()
            return jsonify({"equipment": [dict(r) for r in rows]})
        except Exception:
            return jsonify({"equipment": []})

    @ops_os_bp.post("/ops-os/equipment")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def create_equipment():
        data = request.get_json(silent=True) or {}
        cid = _cid()
        eid = str(data.get("id") or f"eq-{uuid.uuid4().hex[:10]}")
        get_db().execute(
            """
            INSERT INTO site_equipment
                (id, company_id, site_name, name, equipment_type, latitude, longitude, status, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', '{}', ?, ?)
            """,
            (
                eid,
                cid,
                str(data.get("site_name", "")),
                str(data.get("name", "Equipment")),
                str(data.get("equipment_type", "machinery")),
                data.get("latitude"),
                data.get("longitude"),
                now_iso(),
                now_iso(),
            ),
        )
        get_db().commit()
        return jsonify({"id": eid}), 201

    @ops_os_bp.get("/ops-os/hazard-zones")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def list_hazards():
        cid = _cid()
        try:
            rows = get_db().execute("SELECT * FROM site_hazard_zones WHERE company_id = ?", (cid,)).fetchall()
            return jsonify({"hazardZones": [dict(r) for r in rows]})
        except Exception:
            return jsonify({"hazardZones": []})

    @ops_os_bp.post("/ops-os/hazard-zones")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def create_hazard():
        data = request.get_json(silent=True) or {}
        cid = _cid()
        hid = str(data.get("id") or f"hz-{uuid.uuid4().hex[:10]}")
        get_db().execute(
            """
            INSERT INTO site_hazard_zones
                (id, company_id, site_name, label, hazard_level, latitude, longitude, radius_meters, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                hid,
                cid,
                str(data.get("site_name", "")),
                str(data.get("label", "Hazard zone")),
                str(data.get("hazard_level", "high")),
                float(data.get("latitude", 0)),
                float(data.get("longitude", 0)),
                int(data.get("radius_meters", 50)),
                now_iso(),
            ),
        )
        get_db().commit()
        return jsonify({"id": hid}), 201

    flask_app.register_blueprint(ops_os_bp, url_prefix="/api")
