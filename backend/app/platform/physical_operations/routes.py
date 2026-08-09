"""
Physical Operations OS — all 12 capabilities under /api/ops-os/*
"""
from __future__ import annotations

import base64
import json
import time
import uuid

from flask import Blueprint, Response, g, jsonify, request

ops_os_bp = Blueprint("physical_operations", __name__)

_OVERVIEW_CACHE: dict[str, tuple[float, dict]] = {}
_OVERVIEW_TTL_SEC = 25.0
_OVERVIEW_LAYER_CACHE: dict[str, tuple[float, object]] = {}
_OVERVIEW_LAYER_TTL_SEC = 8.0
_LIVE_MAP_CACHE: dict[str, tuple[float, dict]] = {}
_LIVE_MAP_TTL_SEC = 3.0
_COMMAND_CENTER_CACHE: dict[str, tuple[float, dict]] = {}
_COMMAND_CENTER_TTL_SEC = 5.0
_DAILY_BRIEF_CACHE: dict[str, tuple[float, dict]] = {}
_DAILY_BRIEF_TTL_SEC = 6.0
_COPILOT_CONTEXT_CACHE: dict[str, tuple[float, dict]] = {}
_COPILOT_CONTEXT_TTL_SEC = 8.0
_WORKFORCE_GRAPH_CACHE: dict[str, tuple[float, dict]] = {}
_WORKFORCE_GRAPH_TTL_SEC = 8.0


def _micro_cache_get_or_build(
    cache: dict[str, tuple[float, object]],
    key: str,
    ttl_sec: float,
    builder,
    *,
    force: bool = False,
    max_items: int = 300,
    trim_count: int = 60,
    stats: dict[str, int] | None = None,
):
    now = time.monotonic()
    if not force:
        hit = cache.get(key)
        if hit and now - hit[0] < ttl_sec:
            if stats is not None:
                stats["hits"] = int(stats.get("hits", 0)) + 1
            return hit[1]
        if stats is not None:
            stats["misses"] = int(stats.get("misses", 0)) + 1
    elif stats is not None:
        stats["forced"] = int(stats.get("forced", 0)) + 1
    payload = builder()
    cache[key] = (now, payload)
    if len(cache) > max_items:
        oldest = sorted(cache.items(), key=lambda kv: kv[1][0])[:trim_count]
        for stale_key, _ in oldest:
            cache.pop(stale_key, None)
    return payload


def register_physical_operations(flask_app) -> None:
    from backend.server import emit_structured_log, require_auth, require_roles, get_db, log_audit

    from ._common import company_id_from_user, count_on_site, now_iso, today_prefix
    from .digital_twin import build_digital_twin
    from .site_intelligence import build_site_intelligence
    from .security_engine import analyze_security
    from .reputation import build_reputation_leaderboard, compute_worker_reputation
    from .emergency import build_emergency_status, mark_roll_call, start_roll_call, get_emergency
    from .camera_ai import ingest_camera_event
    from .iot_registry import build_iot_overview, list_devices, register_device, record_telemetry
    from .command_center import build_command_center
    from .live_map import build_live_ops_map
    from .workforce_graph import build_workforce_graph
    from .identity_hub import build_identity_hub
    from .copilot import copilot_query, build_copilot_context

    def _payload_bytes(payload) -> int:
        try:
            packed = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
            return len(packed.encode("utf-8"))
        except Exception:
            return 0

    def _emit_ops_perf(endpoint: str, t0: float, payload=None, **fields) -> None:
        duration_ms = max(1, int(round((time.monotonic() - t0) * 1000)))
        event_fields = {"endpoint": endpoint, "durationMs": duration_ms, **fields}
        if payload is not None:
            event_fields["payloadBytes"] = _payload_bytes(payload)
        try:
            emit_structured_log("ops_endpoint_perf", **event_fields)
        except Exception:
            pass

    def _cid() -> str:
        cid = company_id_from_user(g.current_user, request.args)
        if cid:
            return cid
        if g.current_user.get("role") == "superadmin":
            return str(request.args.get("company_id", "") or "").strip()
        return str(g.current_user.get("company_id") or "").strip()

    # ── Fast summary (first paint) ────────────────────────────────────────────
    @ops_os_bp.get("/ops-os/summary")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_summary():
        cid = _cid()
        if not cid and g.current_user.get("role") != "superadmin":
            return jsonify({"error": "company_required"}), 400
        cid = cid or str(request.args.get("company_id", "") or "").strip()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        db = get_db()
        today = today_prefix()
        on_site = int(count_on_site(db, cid, today) or 0)
        open_sec = 0
        try:
            row = db.execute(
                """
                SELECT COUNT(*) AS c FROM security_alerts
                WHERE company_id = ? AND status = 'open'
                """,
                (cid,),
            ).fetchone()
            open_sec = int((row["c"] if row else 0) or 0)
        except Exception:
            open_sec = 0
        emergency = _active_emergency_summary(db, cid)
        cameras = _camera_summary(db, cid)
        autonomous = _autonomous_summary(db, cid)
        copilot = _copilot_layer_summary()
        iot_count = 0
        try:
            row = db.execute(
                "SELECT COUNT(*) AS c FROM iot_devices WHERE company_id = ?",
                (cid,),
            ).fetchone()
            iot_count = int((row["c"] if row else 0) or 0)
        except Exception:
            iot_count = 0
        return jsonify(
            {
                "physicalOperationsOS": True,
                "companyId": cid,
                "fast": True,
                "layers": {
                    "1_digital_twin": {
                        "summary": {"workersOnSite": on_site, "gatesActive": 0, "hazardZones": 0},
                        "totalOnSite": on_site,
                    },
                    "2_ai_security": {
                        "openAlertCount": open_sec,
                        "openAlerts": [],
                        "newFindings": 0,
                    },
                    "3_site_intelligence": {
                        "date": today,
                        "busiestGates": [],
                        "totalEvents24h": 0,
                    },
                    "4_reputation": {"averageScore": 0, "leaderboard": []},
                    "5_emergency": emergency,
                    "6_camera_ai": cameras,
                    "7_iot": {"devices": [{"id": i} for i in range(min(iot_count, 8))], "status": "Registry"},
                    "8_command_center": {
                        "totalOnSite": on_site,
                        "openEmergencies": 1 if emergency.get("active") else 0,
                        "openSecurity": open_sec,
                    },
                    "9_autonomous": autonomous,
                    "10_workforce_graph": {"nodes": [], "edges": []},
                    "11_identity": {"apis": {"gates": "/api/gates"}},
                    "12_copilot": copilot,
                },
            }
        )

    # ── Overview (all 12 layers) ──────────────────────────────────────────────
    @ops_os_bp.get("/ops-os/overview")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_overview():
        t0 = time.monotonic()
        cid = _cid()
        if not cid and g.current_user.get("role") != "superadmin":
            return jsonify({"error": "company_required"}), 400
        db = get_db()
        role = g.current_user.get("role", "")
        cid = cid or str(request.args.get("company_id", "") or "").strip()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        force = str(request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes"}
        deep_force = str(request.args.get("deep_refresh") or "").strip().lower() in {"1", "true", "yes"}
        layer_force = force and deep_force
        cache_key = f"{cid}:{role}"
        now = time.monotonic()
        if not force:
            hit = _OVERVIEW_CACHE.get(cache_key)
            if hit and now - hit[0] < _OVERVIEW_TTL_SEC:
                payload = hit[1]
                _emit_ops_perf(
                    "ops_overview",
                    t0,
                    payload,
                    cacheStatus="hit",
                    cacheAgeMs=int(round((now - hit[0]) * 1000)),
                    force=force,
                    deepRefresh=deep_force,
                )
                return jsonify(hit[1])
        from backend.app.platform.physical_operations.daily_brief import build_daily_ops_brief

        layer_cache_stats = {"hits": 0, "misses": 0, "forced": 0}
        daily = _micro_cache_get_or_build(
            _OVERVIEW_LAYER_CACHE,
            f"daily:{cid}:{role}",
            _OVERVIEW_LAYER_TTL_SEC,
            lambda: build_daily_ops_brief(db, cid),
            force=layer_force,
            stats=layer_cache_stats,
        )
        payload = {
            "physicalOperationsOS": True,
            "companyId": cid,
            "dailyBrief": daily,
            "layers": {
                "1_digital_twin": _micro_cache_get_or_build(
                    _OVERVIEW_LAYER_CACHE,
                    f"digital_twin:{cid}",
                    _OVERVIEW_LAYER_TTL_SEC,
                    lambda: build_digital_twin(db, cid),
                    force=layer_force,
                    stats=layer_cache_stats,
                ),
                "2_ai_security": _micro_cache_get_or_build(
                    _OVERVIEW_LAYER_CACHE,
                    f"ai_security:{cid}",
                    _OVERVIEW_LAYER_TTL_SEC,
                    lambda: analyze_security(db, cid, persist=False),
                    force=layer_force,
                    stats=layer_cache_stats,
                ),
                "3_site_intelligence": _micro_cache_get_or_build(
                    _OVERVIEW_LAYER_CACHE,
                    f"site_intel:{cid}",
                    _OVERVIEW_LAYER_TTL_SEC,
                    lambda: build_site_intelligence(db, cid),
                    force=layer_force,
                    stats=layer_cache_stats,
                ),
                # Keep leaderboard small — full ranking is available via /reputation
                "4_reputation": _micro_cache_get_or_build(
                    _OVERVIEW_LAYER_CACHE,
                    f"reputation:{cid}",
                    _OVERVIEW_LAYER_TTL_SEC,
                    lambda: build_reputation_leaderboard(db, cid, limit=12),
                    force=layer_force,
                    stats=layer_cache_stats,
                ),
                "5_emergency": _micro_cache_get_or_build(
                    _OVERVIEW_LAYER_CACHE,
                    f"emergency:{cid}",
                    _OVERVIEW_LAYER_TTL_SEC,
                    lambda: _active_emergency_summary(db, cid),
                    force=layer_force,
                    stats=layer_cache_stats,
                ),
                "6_camera_ai": _micro_cache_get_or_build(
                    _OVERVIEW_LAYER_CACHE,
                    f"camera_ai:{cid}",
                    _OVERVIEW_LAYER_TTL_SEC,
                    lambda: _camera_summary(db, cid),
                    force=layer_force,
                    stats=layer_cache_stats,
                ),
                "7_iot": _micro_cache_get_or_build(
                    _OVERVIEW_LAYER_CACHE,
                    f"iot:{cid}",
                    _OVERVIEW_LAYER_TTL_SEC,
                    lambda: build_iot_overview(db, cid),
                    force=layer_force,
                    stats=layer_cache_stats,
                ),
                "8_command_center": _micro_cache_get_or_build(
                    _OVERVIEW_LAYER_CACHE,
                    f"command_center:{cid}:{role}",
                    _OVERVIEW_LAYER_TTL_SEC,
                    lambda: build_command_center(db, company_id=cid, role=role),
                    force=layer_force,
                    stats=layer_cache_stats,
                ),
                "9_autonomous": _autonomous_summary(db, cid),
                "10_workforce_graph": _micro_cache_get_or_build(
                    _OVERVIEW_LAYER_CACHE,
                    f"workforce_graph:{cid}",
                    _OVERVIEW_LAYER_TTL_SEC,
                    lambda: build_workforce_graph(db, cid),
                    force=layer_force,
                    stats=layer_cache_stats,
                ),
                "11_identity": _micro_cache_get_or_build(
                    _OVERVIEW_LAYER_CACHE,
                    f"identity:{cid}",
                    _OVERVIEW_LAYER_TTL_SEC,
                    lambda: build_identity_hub(db, cid),
                    force=layer_force,
                    stats=layer_cache_stats,
                ),
                "12_copilot": _copilot_layer_summary(),
                "13_daily_brief": daily,
            },
        }
        _OVERVIEW_CACHE[cache_key] = (now, payload)
        if len(_OVERVIEW_CACHE) > 48:
            oldest = sorted(_OVERVIEW_CACHE.items(), key=lambda kv: kv[1][0])[:12]
            for key, _ in oldest:
                _OVERVIEW_CACHE.pop(key, None)
        _emit_ops_perf(
            "ops_overview",
            t0,
            payload,
            cacheStatus="miss" if not force else "refresh",
            force=force,
            deepRefresh=deep_force,
            layerCacheHits=int(layer_cache_stats.get("hits", 0)),
            layerCacheMisses=int(layer_cache_stats.get("misses", 0)),
            layerCacheForced=int(layer_cache_stats.get("forced", 0)),
        )
        return jsonify(payload)

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
            events24h = int(c["c"] or 0)
            cam_rows = db.execute(
                "SELECT last_seen_at FROM site_cameras WHERE company_id = ?",
                (cid,),
            ).fetchall()
            from backend.app.platform.physical_operations.camera_registry import camera_is_online
            from backend.app.platform.physical_operations.camera_watch import watch_status
            from backend.app.platform.physical_operations.camera_escalation import list_escalations

            online = sum(1 for r in cam_rows if camera_is_online(str(r["last_seen_at"] or "")))
            total = len(cam_rows)
            watch = watch_status(db, cid)
            open_esc = list_escalations(db, cid, limit=5, status="open")
            return {
                "events24h": events24h,
                "camerasTotal": total,
                "camerasOnline": online,
                "watchModeActive": bool(watch.get("watchModeActive")),
                "afterHours": bool(watch.get("afterHours")),
                "watchEnabled": bool(watch.get("enabled")),
                "watchTimezone": watch.get("timezone"),
                "workStart": watch.get("workStart"),
                "workEnd": watch.get("workEnd"),
                "openEscalations": len(open_esc),
                "latestEscalations": open_esc[:3],
            }
        except Exception:
            return {"events24h": 0}

    def _autonomous_summary(db, cid):
        rows = db.execute(
            "SELECT COUNT(*) AS c FROM automation_rules WHERE company_id = ? AND enabled = 1",
            (cid,),
        ).fetchone()
        return {"enabledRules": int((rows["c"] if rows else 0) or 0), "api": "/api/automation/rules"}

    def _copilot_layer_summary():
        from backend.app.core.enterprise_mode import copilot_configured

        return {
            "configured": copilot_configured(),
            "endpoint": "POST /api/ops-os/copilot",
        }

    @ops_os_bp.get("/ops-os/daily-brief")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_daily_brief():
        from backend.app.platform.physical_operations.daily_brief import build_daily_ops_brief

        t0 = time.monotonic()
        cid = _cid()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        role = g.current_user.get("role", "")
        force = str(request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes"}
        cache_key = f"{role}:{cid}"
        now = time.monotonic()
        if not force:
            hit = _DAILY_BRIEF_CACHE.get(cache_key)
            if hit and now - hit[0] < _DAILY_BRIEF_TTL_SEC:
                payload = hit[1]
                _emit_ops_perf(
                    "ops_daily_brief",
                    t0,
                    payload,
                    cacheStatus="hit",
                    cacheAgeMs=int(round((now - hit[0]) * 1000)),
                    force=force,
                )
                return jsonify(hit[1])
        payload = build_daily_ops_brief(get_db(), cid)
        _DAILY_BRIEF_CACHE[cache_key] = (now, payload)
        if len(_DAILY_BRIEF_CACHE) > 120:
            oldest = sorted(_DAILY_BRIEF_CACHE.items(), key=lambda kv: kv[1][0])[:30]
            for key, _ in oldest:
                _DAILY_BRIEF_CACHE.pop(key, None)
        _emit_ops_perf(
            "ops_daily_brief",
            t0,
            payload,
            cacheStatus="miss" if not force else "refresh",
            force=force,
        )
        return jsonify(payload)

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
        force = str(request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes"}
        cache_key = f"{role}:{cid or '-'}"
        now = time.monotonic()
        if not force:
            hit = _COMMAND_CENTER_CACHE.get(cache_key)
            if hit and now - hit[0] < _COMMAND_CENTER_TTL_SEC:
                return jsonify(hit[1])
        payload = build_command_center(get_db(), company_id=cid, role=role)
        _COMMAND_CENTER_CACHE[cache_key] = (now, payload)
        if len(_COMMAND_CENTER_CACHE) > 80:
            oldest = sorted(_COMMAND_CENTER_CACHE.items(), key=lambda kv: kv[1][0])[:20]
            for key, _ in oldest:
                _COMMAND_CENTER_CACHE.pop(key, None)
        return jsonify(payload)

    @ops_os_bp.get("/ops-os/predictions/tomorrow")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_tomorrow_prediction():
        from backend.app.platform.predictions.engine import build_tomorrow_forecast

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        return jsonify(build_tomorrow_forecast(get_db(), cid))

    @ops_os_bp.get("/ops-os/live-map")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_live_map():
        t0 = time.monotonic()
        cid = _cid()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        force = str(request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes"}
        lite = str(request.args.get("lite") or "").strip().lower() in {"1", "true", "yes"}
        cache_key = f"{cid}:{1 if lite else 0}"
        now = time.monotonic()
        if not force:
            hit = _LIVE_MAP_CACHE.get(cache_key)
            if hit and now - hit[0] < _LIVE_MAP_TTL_SEC:
                payload = hit[1]
                _emit_ops_perf(
                    "ops_live_map",
                    t0,
                    payload,
                    cacheStatus="hit",
                    cacheAgeMs=int(round((now - hit[0]) * 1000)),
                    force=force,
                    lite=lite,
                )
                return jsonify(hit[1])

        payload = build_live_ops_map(
            get_db(),
            cid,
            emit_anomalies=not lite,
            north=request.args.get("north"),
            south=request.args.get("south"),
            east=request.args.get("east"),
            west=request.args.get("west"),
        )
        _LIVE_MAP_CACHE[cache_key] = (now, payload)
        if len(_LIVE_MAP_CACHE) > 80:
            oldest = sorted(_LIVE_MAP_CACHE.items(), key=lambda kv: kv[1][0])[:20]
            for key, _ in oldest:
                _LIVE_MAP_CACHE.pop(key, None)
        _emit_ops_perf(
            "ops_live_map",
            t0,
            payload,
            cacheStatus="miss" if not force else "refresh",
            force=force,
            lite=lite,
        )
        return jsonify(payload)

    @ops_os_bp.get("/ops-os/workers/<worker_id>/trail")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_worker_trail(worker_id: str):
        from backend.app.platform.physical_operations.location_trail import get_worker_trail

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        wid = str(worker_id or "").strip()
        if not wid:
            return jsonify({"error": "worker_required"}), 400
        # Ensure worker belongs to company
        row = get_db().execute(
            "SELECT id FROM workers WHERE id = ? AND company_id = ? AND deleted_at IS NULL LIMIT 1",
            (wid, cid),
        ).fetchone()
        if not row:
            return jsonify({"error": "worker_not_found"}), 404
        return jsonify(
            get_worker_trail(
                get_db(),
                company_id=cid,
                worker_id=wid,
                from_iso=request.args.get("from"),
                to_iso=request.args.get("to"),
                limit=int(request.args.get("limit", "500") or 500),
            )
        )

    @ops_os_bp.get("/ops-os/workers/<worker_id>/avatar")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_worker_avatar(worker_id: str):
        cid = _cid()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        wid = str(worker_id or "").strip()
        if not wid:
            return jsonify({"error": "worker_required"}), 400

        row = get_db().execute(
            """
            SELECT photo_data FROM workers
            WHERE id = ? AND company_id = ? AND deleted_at IS NULL AND worker_type = 'worker'
            LIMIT 1
            """,
            (wid, cid),
        ).fetchone()
        if not row:
            return jsonify({"error": "worker_not_found"}), 404

        photo_data = str(row["photo_data"] or "").strip()
        if not photo_data:
            return jsonify({"error": "photo_not_found"}), 404

        if not photo_data.startswith("data:image/") or "," not in photo_data:
            return jsonify({"error": "invalid_photo_data"}), 422
        header, b64_data = photo_data.split(",", 1)
        mime = header[5:].split(";", 1)[0].strip().lower() or "image/png"
        if mime not in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
            mime = "image/png"
        try:
            body = base64.b64decode(b64_data, validate=True)
        except Exception:
            return jsonify({"error": "invalid_photo_data"}), 422

        return Response(
            body,
            mimetype=mime,
            headers={
                "Cache-Control": "private, max-age=300",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @ops_os_bp.get("/ops-os/nearest-workers")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_nearest_workers():
        from backend.app.platform.physical_operations.map_intelligence import find_nearest_workers

        cid = _cid()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        try:
            lat = float(request.args.get("lat"))
            lng = float(request.args.get("lng"))
        except (TypeError, ValueError):
            return jsonify({"error": "lat_lng_required"}), 400
        limit = int(request.args.get("limit", "5") or 5)
        role_q = str(request.args.get("role") or request.args.get("skills") or "").strip()
        radius_raw = request.args.get("radius_m") or request.args.get("radius")
        radius_m = None
        if radius_raw not in (None, ""):
            try:
                radius_m = float(radius_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "invalid_radius"}), 400
        # Reuse live map worker positions (without re-emitting anomalies)
        data = build_live_ops_map(get_db(), cid, emit_anomalies=False)
        nearest, spatial = find_nearest_workers(
            data.get("workersOnSite") or [],
            lat=lat,
            lng=lng,
            limit=limit,
            role_query=role_q,
            radius_meters=radius_m,
            return_meta=True,
        )
        return jsonify(
            {
                "companyId": cid,
                "lat": lat,
                "lng": lng,
                "roleQuery": role_q,
                "radiusMeters": spatial.get("radiusMeters"),
                "count": len(nearest),
                "workers": nearest,
                "spatial": spatial,
            }
        )

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
        t0 = time.monotonic()
        cid = _cid()
        days = int(request.args.get("days", "14"))
        role = g.current_user.get("role", "")
        force = str(request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes"}
        cache_key = f"{role}:{cid}:{days}"
        now = time.monotonic()
        if not force:
            hit = _WORKFORCE_GRAPH_CACHE.get(cache_key)
            if hit and now - hit[0] < _WORKFORCE_GRAPH_TTL_SEC:
                payload = hit[1]
                _emit_ops_perf(
                    "ops_workforce_graph",
                    t0,
                    payload,
                    cacheStatus="hit",
                    cacheAgeMs=int(round((now - hit[0]) * 1000)),
                    force=force,
                    days=days,
                )
                return jsonify(hit[1])
        payload = build_workforce_graph(get_db(), cid, days=days)
        _WORKFORCE_GRAPH_CACHE[cache_key] = (now, payload)
        if len(_WORKFORCE_GRAPH_CACHE) > 120:
            oldest = sorted(_WORKFORCE_GRAPH_CACHE.items(), key=lambda kv: kv[1][0])[:30]
            for key, _ in oldest:
                _WORKFORCE_GRAPH_CACHE.pop(key, None)
        _emit_ops_perf(
            "ops_workforce_graph",
            t0,
            payload,
            cacheStatus="miss" if not force else "refresh",
            force=force,
            days=days,
        )
        return jsonify(payload)

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
        t0 = time.monotonic()
        cid = _cid()
        role = g.current_user.get("role", "")
        force = str(request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes"}
        cache_key = f"{role}:{cid}"
        now = time.monotonic()
        if not force:
            hit = _COPILOT_CONTEXT_CACHE.get(cache_key)
            if hit and now - hit[0] < _COPILOT_CONTEXT_TTL_SEC:
                payload = hit[1]
                _emit_ops_perf(
                    "ops_copilot_context",
                    t0,
                    payload,
                    cacheStatus="hit",
                    cacheAgeMs=int(round((now - hit[0]) * 1000)),
                    force=force,
                )
                return jsonify(hit[1])
        payload = build_copilot_context(get_db(), cid, role)
        _COPILOT_CONTEXT_CACHE[cache_key] = (now, payload)
        if len(_COPILOT_CONTEXT_CACHE) > 120:
            oldest = sorted(_COPILOT_CONTEXT_CACHE.items(), key=lambda kv: kv[1][0])[:30]
            for key, _ in oldest:
                _COPILOT_CONTEXT_CACHE.pop(key, None)
        _emit_ops_perf(
            "ops_copilot_context",
            t0,
            payload,
            cacheStatus="miss" if not force else "refresh",
            force=force,
        )
        return jsonify(payload)

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
