"""
Enterprise endpoints for gaps not yet exposed or missing from modular layer.
"""
from __future__ import annotations

import base64
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, g, jsonify, request

enterprise_bp = Blueprint("enterprise", __name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _company_id() -> str:
    user = g.current_user
    if user.get("role") == "superadmin":
        return (
            str(request.args.get("company_id", "") or "").strip()
            or str(user.get("preview_company_id") or "").strip()
            or str(user.get("company_id") or "").strip()
        )
    return str(user.get("company_id") or "").strip()


def _parse_geofence_coordinates(data: dict) -> tuple[float, float] | None:
    raw_lat = data.get("latitude")
    raw_lng = data.get("longitude")
    if raw_lat is None or raw_lng is None:
        return None
    try:
        lat = float(raw_lat)
        lng = float(raw_lng)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None
    return lat, lng


def _validate_geofence_company(db, company_id: str):
    cid = str(company_id or "").strip()
    if not cid:
        return None, (jsonify({"error": "company_required", "message": "Bitte zuerst eine Firma auswählen."}), 400)
    row = db.execute(
        "SELECT id FROM companies WHERE id = ? AND deleted_at IS NULL",
        (cid,),
    ).fetchone()
    if not row:
        return None, (jsonify({"error": "company_not_found", "message": "Firma nicht gefunden."}), 400)
    return cid, None


def _post_form_with_retry(url: str, payload: dict[str, str], bearer: str, timeout_s: int = 30) -> dict:
    """Simple retry wrapper for third-party integration HTTP posts."""
    from urllib import parse, request as urlrequest

    encoded = parse.urlencode(payload).encode()
    last_err = None
    for attempt in range(3):
        try:
            req = urlrequest.Request(
                url,
                data=encoded,
                headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urlrequest.urlopen(req, timeout=timeout_s) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            last_err = exc
            if attempt < 2:
                time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"external_post_failed: {last_err}")


def register_enterprise_routes(flask_app):
    from backend.server import require_auth, require_roles

    # ── Geofence admin CRUD ───────────────────────────────────────────────────
    @enterprise_bp.get("/geofences/admin")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_list_geofences():
        from backend.server import get_db

        cid = _company_id()
        rows = get_db().execute(
            "SELECT * FROM geofences WHERE company_id = ? ORDER BY site_name",
            (str(cid),),
        ).fetchall()
        return jsonify({"geofences": [dict(r) for r in rows]})

    @enterprise_bp.post("/geofences/admin")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_create_geofence():
        from backend.server import get_db

        data = request.get_json(silent=True) or {}
        db = get_db()
        cid, company_error = _validate_geofence_company(db, _company_id())
        if company_error:
            return company_error

        site_name = str(data.get("site_name", "")).strip()
        if not site_name:
            return jsonify({"error": "site_name_required", "message": "Baustellenname fehlt."}), 400

        coords = _parse_geofence_coordinates(data)
        if not coords:
            return jsonify(
                {
                    "error": "invalid_coordinates",
                    "message": "Ungültige Koordinaten — bitte Karte anklicken oder GPS nutzen.",
                }
            ), 400
        lat, lng = coords

        try:
            radius = int(data.get("radius_meters", 25))
        except (TypeError, ValueError):
            radius = 25
        radius = max(5, min(radius, 5000))

        gf_id = f"gf-{uuid.uuid4().hex[:10]}"
        db.execute(
            """
            INSERT INTO geofences (id, company_id, site_name, latitude, longitude, radius_meters, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (gf_id, cid, site_name, lat, lng, radius, _now_iso()),
        )
        db.commit()
        return jsonify({"id": gf_id}), 201

    @enterprise_bp.put("/geofences/admin/<gf_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_update_geofence(gf_id: str):
        from backend.server import get_db

        data = request.get_json(silent=True) or {}
        db = get_db()
        cid, company_error = _validate_geofence_company(db, _company_id())
        if company_error:
            return company_error

        lat = data.get("latitude") if "latitude" in data else None
        lng = data.get("longitude") if "longitude" in data else None
        if lat is not None or lng is not None:
            coords = _parse_geofence_coordinates({"latitude": lat, "longitude": lng})
            if not coords:
                return jsonify({"error": "invalid_coordinates", "message": "Ungültige Koordinaten."}), 400
            lat, lng = coords

        radius = data.get("radius_meters")
        if radius is not None:
            try:
                radius = max(5, min(int(radius), 5000))
            except (TypeError, ValueError):
                return jsonify({"error": "invalid_radius", "message": "Ungültiger Radius."}), 400

        db.execute(
            """
            UPDATE geofences
            SET site_name = COALESCE(?, site_name),
                latitude = COALESCE(?, latitude),
                longitude = COALESCE(?, longitude),
                radius_meters = COALESCE(?, radius_meters),
                active = COALESCE(?, active)
            WHERE id = ? AND company_id = ?
            """,
            (
                data.get("site_name"),
                lat,
                lng,
                radius,
                data.get("active"),
                gf_id,
                cid,
            ),
        )
        db.commit()
        return jsonify({"ok": True})

    # ── Workforce heatmap ─────────────────────────────────────────────────────
    @enterprise_bp.get("/analytics/workforce-heatmap")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def workforce_heatmap():
        from backend.app.db.connection import get_read_connection

        cid = _company_id()
        days = min(30, max(1, int(request.args.get("days", "7"))))
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        with get_read_connection() as db:
            rows = db.execute(
                """
                SELECT substr(al.timestamp, 1, 10) AS day,
                       substr(al.timestamp, 12, 2) AS hour,
                       al.direction,
                       COUNT(*) AS c
                FROM access_logs al
                JOIN workers w ON w.id = al.worker_id
                WHERE w.company_id = ? AND al.timestamp >= ?
                GROUP BY day, hour, al.direction
                ORDER BY day, hour
                """,
                (cid, since),
            ).fetchall()
        cells = [dict(r) for r in rows]
        return jsonify({"days": days, "cells": cells})

    # ── Contractor intelligence ───────────────────────────────────────────────
    @enterprise_bp.get("/contractors/intelligence")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def contractor_intelligence():
        from backend.app.db.connection import get_read_connection

        cid = _company_id()
        with get_read_connection() as db:
            rows = db.execute(
                """
                SELECT w.id, w.first_name, w.last_name, w.status, w.badge_id,
                       COUNT(al.id) AS access_count,
                       MAX(al.timestamp) AS last_access
                FROM workers w
                LEFT JOIN access_logs al ON al.worker_id = w.id
                WHERE w.company_id = ? AND w.worker_type = 'contractor' AND w.deleted_at IS NULL
                GROUP BY w.id
                ORDER BY access_count DESC
                LIMIT 200
                """,
                (cid,),
            ).fetchall()
        return jsonify({"contractors": [dict(r) for r in rows]})

    # ── Emergency response ────────────────────────────────────────────────────
    @enterprise_bp.post("/emergency/trigger")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def emergency_trigger():
        from backend.server import get_db, log_audit
        from backend.app.platform.events.bus import publish_event

        data = request.get_json(silent=True) or {}
        cid = _company_id()
        eid = f"emg-{uuid.uuid4().hex[:10]}"
        message = str(data.get("message", "Emergency")).strip()
        get_db().execute(
            """
            INSERT INTO emergency_events (id, company_id, message, status, created_by, created_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
            (eid, cid, message, str(g.current_user.get("id", "")), _now_iso()),
        )
        get_db().commit()
        publish_event("emergency.triggered", cid, {"emergency_id": eid, "message": message})
        log_audit("emergency.triggered", message, company_id=cid, actor=g.current_user)
        return jsonify({"id": eid, "status": "active"}), 201

    @enterprise_bp.get("/emergency/active")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def emergency_active():
        from backend.server import get_db

        cid = _company_id()
        rows = get_db().execute(
            "SELECT * FROM emergency_events WHERE company_id = ? AND status = 'active' ORDER BY created_at DESC",
            (cid,),
        ).fetchall()
        return jsonify({"emergencies": [dict(r) for r in rows]})

    # ── Visitor temporary access ──────────────────────────────────────────────
    @enterprise_bp.post("/visitors/temporary-access")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def visitor_temporary_access():
        data = request.get_json(silent=True) or {}
        hours = min(72, max(1, int(data.get("hours", 8))))
        end_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0).isoformat() + "Z"
        return jsonify(
            {
                "useEndpoint": "POST /api/workers",
                "payloadTemplate": {
                    "workerType": "visitor",
                    "firstName": data.get("first_name", "Guest"),
                    "lastName": data.get("last_name", "Visitor"),
                    "visitorCompany": data.get("visitor_company", "Guest"),
                    "visitPurpose": data.get("visit_purpose", "Temporary access"),
                    "hostName": data.get("host_name", g.current_user.get("username", "Admin")),
                    "visitEndAt": end_at,
                    "companyId": _company_id(),
                },
            }
        )

    # ── Dynamic access permissions ────────────────────────────────────────────
    @enterprise_bp.get("/access-permissions")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def list_access_permissions():
        from backend.server import get_db

        rows = get_db().execute(
            "SELECT * FROM access_permissions WHERE company_id = ? ORDER BY created_at DESC",
            (_company_id(),),
        ).fetchall()
        return jsonify({"permissions": [dict(r) for r in rows]})

    @enterprise_bp.post("/access-permissions")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def create_access_permission():
        from backend.server import get_db

        data = request.get_json(silent=True) or {}
        pid = f"ap-{uuid.uuid4().hex[:10]}"
        get_db().execute(
            """
            INSERT INTO access_permissions
                (id, company_id, worker_id, zone_id, allowed_from, allowed_until, rules_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid,
                _company_id(),
                data.get("worker_id"),
                data.get("zone_id"),
                data.get("allowed_from"),
                data.get("allowed_until"),
                json.dumps(data.get("rules") or {}),
                _now_iso(),
            ),
        )
        get_db().commit()
        return jsonify({"id": pid}), 201

    # ── Automation rules ──────────────────────────────────────────────────────
    @enterprise_bp.get("/automation/rules")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def automation_list():
        from backend.server import get_db
        from .automation_engine import list_rules

        return jsonify({"rules": list_rules(get_db(), _company_id())})

    @enterprise_bp.post("/automation/rules")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def automation_create():
        from backend.server import get_db
        from .automation_engine import create_rule

        return jsonify(create_rule(get_db(), _company_id(), request.get_json(silent=True) or {})), 201

    # ── Ops: access log archival ───────────────────────────────────────────────
    @enterprise_bp.post("/ops/archive-access-logs")
    @require_auth
    @require_roles("superadmin")
    def archive_access_logs_route():
        from backend.server import get_db
        from backend.app.tasks.access_logs_archive import archive_access_logs

        return jsonify(archive_access_logs(get_db()))

    # ── Integrations ──────────────────────────────────────────────────────────
    @enterprise_bp.get("/integrations")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def integrations_list():
        from backend.server import get_db

        rows = get_db().execute(
            "SELECT id, company_id, provider, status, config_json, created_at, updated_at FROM integration_connections WHERE company_id = ?",
            (_company_id(),),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            cfg = json.loads(item.pop("config_json") or "{}")
            from .integration_oauth import oauth_config_for_api

            safe = {k: "***" if "secret" in k.lower() or "token" in k.lower() else v for k, v in cfg.items()}
            if cfg.get("oauth"):
                safe["oauth"] = oauth_config_for_api(cfg)
            item["config"] = safe
            out.append(item)
        return jsonify({"integrations": out})

    @enterprise_bp.post("/integrations/<provider>/connect")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def integrations_connect(provider: str):
        from backend.server import get_db

        if provider not in ("microsoft365", "google_workspace", "payroll", "sap", "oracle", "datev"):
            return jsonify({"error": "unknown_provider"}), 400
        data = request.get_json(silent=True) or {}
        from .integration_oauth import merge_oauth_config

        if isinstance(data.get("oauth"), dict):
            data = merge_oauth_config({k: v for k, v in data.items() if k != "oauth"}, data["oauth"])
        cid = _company_id()
        iid = f"int-{uuid.uuid4().hex[:10]}"
        existing = get_db().execute(
            "SELECT id FROM integration_connections WHERE company_id = ? AND provider = ?",
            (cid, provider),
        ).fetchone()
        if existing:
            get_db().execute(
                """
                UPDATE integration_connections
                SET status = 'connected', config_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(data), _now_iso(), existing["id"]),
            )
            iid = existing["id"]
        else:
            get_db().execute(
                """
                INSERT INTO integration_connections (id, company_id, provider, status, config_json, created_at, updated_at)
                VALUES (?, ?, ?, 'connected', ?, ?, ?)
                """,
                (iid, cid, provider, json.dumps(data), _now_iso(), _now_iso()),
            )
        get_db().commit()
        return jsonify({"id": iid, "provider": provider, "status": "connected"}), 201

    @enterprise_bp.post("/integrations/<provider>/sync")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def integrations_sync(provider: str):
        """Trigger integration sync job (queued when Redis available)."""
        from backend.app.tasks import enqueue
        from .integrations import provider_connectivity
        from backend.server import get_db

        if provider not in ("microsoft365", "google_workspace", "payroll", "sap", "oracle", "datev"):
            return jsonify({"error": "unknown_provider"}), 400
        cid = _company_id()

        def _sync_job(company_id: int, prov: str):
            from backend.app.platform.events.bus import publish_event
            from .integration_sync import sync_provider

            db = get_db()
            row = db.execute(
                "SELECT config_json FROM integration_connections WHERE company_id = ? AND provider = ? LIMIT 1",
                (company_id, prov),
            ).fetchone()
            cfg = json.loads((row["config_json"] if row else "{}") or "{}")
            from .integration_oauth import extract_oauth_config

            cfg_for_sync = dict(cfg)
            cfg_for_sync.update(extract_oauth_config(cfg))
            sync_result = sync_provider(prov, cfg_for_sync, company_id=company_id)
            probe = sync_result if sync_result.get("provider") else provider_connectivity(prov, cfg)
            status = "connected" if sync_result.get("ok") else "degraded"
            db.execute(
                """
                UPDATE integration_connections
                SET status = ?, updated_at = ?
                WHERE company_id = ? AND provider = ?
                """,
                (status, _now_iso(), company_id, prov),
            )
            db.commit()

            publish_event(
                f"integration.{prov}.sync_completed",
                company_id,
                {"provider": prov, "sync": sync_result, "status": status},
            )
            return {"provider": prov, "sync": sync_result, "status": status}

        try:
            job = enqueue("default", _sync_job, company_id=cid, prov=provider)
            if job is not None:
                return jsonify({"queued": True, "provider": provider})
        except Exception:
            pass
        result = _sync_job(cid, provider)
        return jsonify({"queued": False, "provider": provider, "completed": True, "result": result})

    # ── Stripe billing (legacy /api paths — delegate to billing domain) ───────
    @enterprise_bp.post("/billing/stripe/checkout-session")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def stripe_checkout():
        from backend.app.domains.billing import stripe_service
        from backend.server import get_db

        if not stripe_service.stripe_configured():
            return jsonify({"error": "stripe_not_configured", "hint": "Set STRIPE_SECRET_KEY"}), 503
        cid = _company_id()
        if not cid:
            return jsonify({"error": "forbidden_company"}), 403
        data = request.get_json(silent=True) or {}
        try:
            result = stripe_service.create_checkout_session(
                get_db(),
                cid,
                plan=str(data.get("plan") or "starter"),
                annual=bool(data.get("annual")),
                success_url=str(data.get("success_url") or ""),
                cancel_url=str(data.get("cancel_url") or ""),
            )
            return jsonify(result)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"error": "stripe_upstream_failed", "detail": str(exc)}), 502

    @enterprise_bp.post("/billing/stripe/webhook")
    def stripe_webhook():
        from backend.app.domains.billing import stripe_service
        from backend.server import get_db

        payload_raw = request.get_data() or b""
        sig = request.headers.get("Stripe-Signature") or ""
        if stripe_service.webhook_signature_required():
            if not stripe_service._webhook_secret():
                return jsonify({"error": "webhook_secret_missing"}), 503
            if not stripe_service.verify_webhook_signature(payload_raw, sig):
                return jsonify({"error": "invalid_signature"}), 400
        elif stripe_service._webhook_secret():
            if not stripe_service.verify_webhook_signature(payload_raw, sig):
                return jsonify({"error": "invalid_signature"}), 400
        try:
            event = request.get_json(silent=True) or {}
            if not event and payload_raw:
                event = json.loads(payload_raw.decode("utf-8"))
        except Exception:
            return jsonify({"error": "invalid_payload"}), 400
        try:
            result = stripe_service.handle_webhook_event(get_db(), event)
            return jsonify({"received": True, **result})
        except Exception as exc:
            return jsonify({"error": "webhook_processing_failed", "detail": str(exc)}), 500

    # ── Plugin marketplace ────────────────────────────────────────────────────
    @enterprise_bp.get("/marketplace/plugins")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def marketplace_plugins():
        from backend.server import get_db

        catalog = [
            {"id": "plugin-geofence-pro", "name": "Geofence Pro", "category": "access"},
            {"id": "plugin-payroll-export", "name": "Payroll Export", "category": "billing"},
            {"id": "plugin-ai-insights", "name": "AI Insights", "category": "ai"},
        ]
        installed = get_db().execute(
            "SELECT plugin_id, status, installed_at FROM company_plugins WHERE company_id = ?",
            (_company_id(),),
        ).fetchall()
        return jsonify({"catalog": catalog, "installed": [dict(r) for r in installed]})

    @enterprise_bp.post("/marketplace/plugins/<plugin_id>/install")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def marketplace_install(plugin_id: str):
        from backend.server import get_db

        get_db().execute(
            """
            INSERT INTO company_plugins (company_id, plugin_id, status, installed_at)
            VALUES (?, ?, 'active', ?)
            ON CONFLICT(company_id, plugin_id) DO UPDATE SET status='active', installed_at=excluded.installed_at
            """,
            (_company_id(), plugin_id, _now_iso()),
        )
        get_db().commit()
        return jsonify({"ok": True, "plugin_id": plugin_id})

    @enterprise_bp.get("/marketplace/plugins/sandbox-policy")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def marketplace_sandbox_policy():
        return jsonify(
            {
                "sandbox": True,
                "allowedScopes": ["read:workers", "read:access_logs", "write:webhooks"],
                "isolatedBy": "company_id",
                "note": "Plugins run against tenant-scoped APIs only; no cross-company data",
            }
        )

    # ── API marketplace catalog ───────────────────────────────────────────────
    @enterprise_bp.get("/marketplace/apis")
    def api_marketplace():
        return jsonify(
            {
                "apis": [
                    {"id": "workers", "version": "v1", "path": "/api/v1/workers"},
                    {"id": "access-logs", "version": "v1", "path": "/api/v1/access-logs/recent"},
                    {"id": "webhooks", "version": "v1", "path": "/api/developer/webhooks"},
                    {"id": "events-stream", "version": "v1", "path": "/api/v1/stream/events"},
                ]
            }
        )

    # ── Behavior patterns ─────────────────────────────────────────────────────
    @enterprise_bp.get("/analytics/behavior-patterns")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def behavior_patterns():
        from backend.app.db.connection import get_read_connection
        from backend.app.platform.ai.behavior_patterns import analyze_behavior_patterns

        days = min(90, max(1, int(request.args.get("days", "14"))))
        with get_read_connection() as db:
            return jsonify(analyze_behavior_patterns(db, _company_id(), days=days))

    # ── Payroll export preview ──────────────────────────────────────────────────
    @enterprise_bp.get("/integrations/payroll/export-preview")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def payroll_export_preview():
        from backend.server import get_db
        from .payroll_adapter import payroll_export_preview as preview

        period = (request.args.get("period") or "").strip()[:7]
        return jsonify(preview(get_db(), _company_id(), period=period))

    @enterprise_bp.get("/integrations/datev/status")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def datev_integration_status():
        from backend.server import get_db
        from .datev_client import datev_env_configured, datev_status_from_config

        db = get_db()
        cid = _company_id()
        row = db.execute(
            "SELECT config_json, status FROM integration_connections WHERE company_id = ? AND provider = ?",
            (cid, "datev"),
        ).fetchone()
        cfg = json.loads((row["config_json"] if row else "{}") or "{}")
        status = datev_status_from_config(cfg)
        status["connectionStatus"] = (row["status"] if row else "") or "disconnected"
        status["envConfigured"] = datev_env_configured()
        return jsonify(status)

    @enterprise_bp.get("/integrations/datev/oauth/start")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def datev_oauth_start():
        from .datev_client import build_datev_authorize_url

        payload = build_datev_authorize_url(company_id=_company_id())
        if not payload.get("ok"):
            return jsonify(payload), 400
        return jsonify(payload)

    @enterprise_bp.get("/integrations/payroll/datev-csv")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def payroll_datev_csv():
        from flask import make_response

        from backend.server import get_db
        from .payroll_adapter import build_datev_payroll_csv

        period = (request.args.get("period") or "").strip()[:7]
        company_id = _company_id()
        csv_text = build_datev_payroll_csv(get_db(), company_id, period=period)
        filename = f"datev-lohn-{company_id}-{period or 'gesamt'}.csv"
        response = make_response(csv_text)
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @enterprise_bp.get("/integrations/sap/export-preview")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def sap_export_preview_route():
        from backend.server import get_db
        from .erp_adapters import sap_export_preview

        period = (request.args.get("period") or "").strip()[:7]
        return jsonify(sap_export_preview(get_db(), _company_id(), period=period))

    @enterprise_bp.get("/integrations/oracle/export-preview")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def oracle_export_preview_route():
        from backend.server import get_db
        from .erp_adapters import oracle_export_preview

        period = (request.args.get("period") or "").strip()[:7]
        return jsonify(oracle_export_preview(get_db(), _company_id(), period=period))

    @enterprise_bp.post("/integrations/sap/export")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def sap_export_push_route():
        from backend.server import get_db
        from .erp_adapters import push_erp_export
        from .integration_oauth import extract_oauth_config

        data = request.get_json(silent=True) or {}
        period = str(data.get("period") or request.args.get("period") or "").strip()[:7]
        dry_run = bool(data.get("dryRun") or data.get("dry_run"))
        cid = _company_id()
        row = get_db().execute(
            "SELECT config_json FROM integration_connections WHERE company_id = ? AND provider = 'sap' LIMIT 1",
            (cid,),
        ).fetchone()
        cfg = json.loads((row["config_json"] if row else "{}") or "{}")
        cfg.update(extract_oauth_config(cfg))
        return jsonify(push_erp_export(get_db(), cid, "sap", cfg, period=period, dry_run=dry_run))

    @enterprise_bp.post("/integrations/oracle/export")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def oracle_export_push_route():
        from backend.server import get_db
        from .erp_adapters import push_erp_export
        from .integration_oauth import extract_oauth_config

        data = request.get_json(silent=True) or {}
        period = str(data.get("period") or request.args.get("period") or "").strip()[:7]
        dry_run = bool(data.get("dryRun") or data.get("dry_run"))
        cid = _company_id()
        row = get_db().execute(
            "SELECT config_json FROM integration_connections WHERE company_id = ? AND provider = 'oracle' LIMIT 1",
            (cid,),
        ).fetchone()
        cfg = json.loads((row["config_json"] if row else "{}") or "{}")
        cfg.update(extract_oauth_config(cfg))
        return jsonify(push_erp_export(get_db(), cid, "oracle", cfg, period=period, dry_run=dry_run))

    @enterprise_bp.get("/integrations/<provider>/health")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def integration_health(provider: str):
        from backend.server import get_db
        from .integrations import provider_connectivity
        from .integration_oauth import extract_oauth_config

        if provider not in ("microsoft365", "google_workspace", "payroll", "sap", "oracle"):
            return jsonify({"error": "unknown_provider"}), 400
        row = get_db().execute(
            "SELECT config_json FROM integration_connections WHERE company_id = ? AND provider = ? LIMIT 1",
            (_company_id(), provider),
        ).fetchone()
        cfg = json.loads((row["config_json"] if row else "{}") or "{}")
        cfg.update(extract_oauth_config(cfg))
        return jsonify({"provider": provider, "health": provider_connectivity(provider, cfg)})

    # ── Document OCR + AI analysis ────────────────────────────────────────────
    @enterprise_bp.post("/documents/ocr-analyze")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def document_ocr_analyze():
        from backend.server import get_db
        from backend.app.platform.ai.assistant import is_ai_configured, natural_language_query

        data = request.get_json(silent=True) or {}
        b64 = str(data.get("file_data_b64", "")).strip()
        if not b64:
            return jsonify({"error": "missing_file"}), 400
        raw = base64.b64decode(b64.split(",", 1)[-1])
        from backend.app.platform.documents.ocr_pipeline import extract_text_from_bytes

        ocr_result = extract_text_from_bytes(raw, str(data.get("filename") or ""))
        text_guess = ocr_result.get("text") or ""

        doc_id = f"ocr-{uuid.uuid4().hex[:10]}"
        get_db().execute(
            """
            INSERT INTO document_ocr_results (id, company_id, extracted_text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (doc_id, _company_id(), text_guess, _now_iso()),
        )
        get_db().commit()
        ai = None
        if is_ai_configured() and text_guess:
            ai = natural_language_query(
                _company_id(),
                "Summarize this document and list compliance risks.",
                {"ocr_text": text_guess[:4000]},
            )
        return jsonify(
            {
                "id": doc_id,
                "extracted_text": text_guess[:2000],
                "engines": ocr_result.get("engines", []),
                "ai": ai,
            }
        )

    # ── Operations intelligence ───────────────────────────────────────────────
    @enterprise_bp.get("/operations/intelligence/optimization")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_optimization():
        from backend.app.db.connection import get_read_connection
        from backend.app.platform.operations.intelligence import workforce_optimization

        with get_read_connection() as db:
            return jsonify(workforce_optimization(db, _company_id()))

    @enterprise_bp.get("/operations/intelligence/allocation")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_allocation():
        from backend.app.db.connection import get_read_connection
        from backend.app.platform.operations.intelligence import resource_allocation

        with get_read_connection() as db:
            return jsonify(resource_allocation(db, _company_id()))

    @enterprise_bp.get("/operations/intelligence/scheduling")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_scheduling():
        from backend.app.db.connection import get_read_connection
        from backend.app.platform.operations.intelligence import ai_scheduling_hints

        with get_read_connection() as db:
            return jsonify(ai_scheduling_hints(db, _company_id()))

    @enterprise_bp.get("/operations/intelligence/forecast")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ops_forecast():
        from backend.app.db.connection import get_read_connection
        from backend.app.platform.operations.intelligence import predictive_workforce_plan

        days = min(60, max(1, int(request.args.get("days", "14"))))
        with get_read_connection() as db:
            return jsonify(predictive_workforce_plan(db, _company_id(), horizon_days=days))

    @enterprise_bp.get("/platform/global-readiness")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def global_readiness():
        import os
        from backend.app.core.cloud_profile import get_cloud_profile
        from backend.app.health.dr_status import collect_dr_status
        from backend.app.platform.multi_region.residency import (
            current_deployment_region,
            get_company_residency,
        )
        from backend.server import DB_PATH, get_db

        cid = _company_id()
        return jsonify(
            {
                "cloud": get_cloud_profile(),
                "dr": collect_dr_status(Path(DB_PATH)),
                "dataResidency": get_company_residency(get_db(), cid),
                "deploymentRegion": current_deployment_region(),
                "expansion": {
                    "multiRegionReady": os.getenv("BAUPASS_REGION_STRATEGY", "single") == "multi",
                    "activeRegions": [r for r in (os.getenv("BAUPASS_ACTIVE_REGIONS") or "").split(",") if r.strip()],
                    "enforceResidency": os.getenv("BAUPASS_ENFORCE_DATA_RESIDENCY", "0") in {"1", "true", "yes"},
                    "documentation": "docs/multi-region-readiness-AR.md",
                },
                "domainsSplitDeferred": True,
            }
        )

    @enterprise_bp.get("/platform/capabilities")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def platform_capabilities():
        from backend.app.platform.capabilities import collect_platform_capabilities
        from backend.server import DB_PATH

        return jsonify(collect_platform_capabilities(Path(DB_PATH)))

    @enterprise_bp.get("/platform/setup-status")
    def platform_setup_status():
        from backend.app.platform.setup_status import collect_setup_status

        return jsonify(collect_setup_status())

    @enterprise_bp.get("/platform/enterprise-catalog/preview")
    def platform_enterprise_catalog_preview():
        """Public read-only catalog (no auth) — demo plan professional for visibility."""
        from backend.app.platform.enterprise_catalog import get_enterprise_catalog
        from backend.app.platform.plan_entitlements import apply_plan_to_catalog, build_plan_comparison_matrix

        catalog = apply_plan_to_catalog(get_enterprise_catalog(), "professional")
        catalog["preview"] = True
        catalog["planComparison"] = build_plan_comparison_matrix(get_enterprise_catalog())
        return jsonify(catalog)

    @enterprise_bp.get("/platform/enterprise-catalog")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def platform_enterprise_catalog():
        from backend.app.platform.enterprise_catalog import get_enterprise_catalog
        from backend.app.platform.plan_entitlements import apply_plan_to_catalog, build_plan_comparison_matrix
        from backend.server import get_company_plan, get_db, normalize_company_plan

        catalog = get_enterprise_catalog()
        db = get_db()
        role = g.current_user.get("role")
        cid = g.current_user.get("company_id")
        if role == "superadmin":
            cid = (
                request.args.get("company_id")
                or getattr(g, "preview_company_id", "")
                or g.current_user.get("preview_company_id")
                or cid
            )
        plan = get_company_plan(db, cid) if cid else "starter"
        if role == "superadmin" and request.args.get("plan"):
            plan = normalize_company_plan(request.args.get("plan"))
        from backend.app.domains.billing import stripe_service

        payload = apply_plan_to_catalog(catalog, plan)
        payload["planComparison"] = build_plan_comparison_matrix(catalog)
        payload["resolvedCompanyId"] = cid or ""
        payload["billing"] = {
            "stripeConfigured": stripe_service.stripe_configured(),
            "selfServeCheckout": stripe_service.stripe_configured() and role == "company-admin",
        }
        return jsonify(payload)

    @enterprise_bp.get("/platform/entitlements")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def platform_entitlements():
        from backend.app.platform.enterprise_catalog import get_enterprise_catalog
        from backend.app.platform.plan_entitlements import (
            PLAN_META,
            PLAN_ORDER,
            apply_plan_to_catalog,
            build_plan_comparison_matrix,
        )
        from backend.server import get_company_plan, get_plan_features, get_db

        db = get_db()
        role = g.current_user.get("role")
        cid = g.current_user.get("company_id")
        if role == "superadmin":
            cid = (
                request.args.get("company_id")
                or getattr(g, "preview_company_id", "")
                or g.current_user.get("preview_company_id")
                or cid
            )
        plan = get_company_plan(db, cid) if cid else "starter"
        catalog = apply_plan_to_catalog(get_enterprise_catalog(), plan)
        return jsonify(
            {
                "plan": plan,
                "resolvedCompanyId": cid or "",
                "planMeta": PLAN_META.get(plan, {}),
                "planOrder": list(PLAN_ORDER),
                "legacyFeatures": get_plan_features(plan),
                "entitlements": catalog.get("entitlements"),
                "planComparison": build_plan_comparison_matrix(get_enterprise_catalog()),
                "layersSummary": [
                    {
                        "id": L["id"],
                        "number": L["number"],
                        "titleAr": L["titleAr"],
                        "enabledCount": L.get("enabledCount"),
                        "totalCount": L.get("totalCount"),
                    }
                    for L in catalog.get("layers", [])
                ],
            }
        )

    @enterprise_bp.get("/platform/database-status")
    @require_auth
    @require_roles("superadmin")
    def platform_database_status():
        from backend.app.database import get_database_health, postgres_preflight
        from backend.app.db.runtime import postgres_runtime_enabled
        from backend.app.db.pg_bootstrap import core_schema_ready, missing_core_tables

        payload = {
            "postgresRuntime": postgres_runtime_enabled(),
            "health": get_database_health(),
            "preflight": postgres_preflight() if postgres_runtime_enabled() else {"status": "skipped"},
            "coreSchemaReady": core_schema_ready() if postgres_runtime_enabled() else None,
            "missingTables": missing_core_tables(force_refresh=True) if postgres_runtime_enabled() else [],
        }
        payload["ok"] = (
            not postgres_runtime_enabled()
            or (payload.get("preflight", {}).get("status") == "ok" and payload.get("coreSchemaReady"))
        )
        return jsonify(payload)

    @enterprise_bp.put("/platform/companies/<company_id>/data-residency")
    @require_auth
    @require_roles("superadmin")
    def set_data_residency(company_id: str):
        from backend.server import get_db
        from backend.app.platform.multi_region.residency import set_company_residency

        data = request.get_json(silent=True) or {}
        region = str(data.get("data_region") or data.get("region") or "").strip()
        policy = str(data.get("policy") or "strict").strip()
        return jsonify(set_company_residency(get_db(), company_id, region, policy))

    @enterprise_bp.get("/platform/companies/<company_id>/data-residency")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def get_data_residency(company_id: str):
        from backend.server import get_db
        from backend.app.platform.multi_region.residency import get_company_residency

        user_cid = str(g.current_user.get("company_id") or "").strip()
        if g.current_user.get("role") != "superadmin" and user_cid != str(company_id).strip():
            return jsonify({"error": "forbidden"}), 403
        return jsonify(get_company_residency(get_db(), company_id))

    # ── Smart expiry prediction ───────────────────────────────────────────────
    @enterprise_bp.get("/compliance/expiry-predictions")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def expiry_predictions():
        from backend.app.db.connection import get_read_connection

        cid = _company_id()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with get_read_connection() as db:
            rows = db.execute(
                """
                SELECT wd.id, wd.worker_id, wd.doc_type, wd.expiry_date, w.first_name, w.last_name
                FROM worker_documents wd
                JOIN workers w ON w.id = wd.worker_id
                WHERE w.company_id = ? AND wd.expiry_date IS NOT NULL AND wd.expiry_date >= ?
                ORDER BY wd.expiry_date ASC
                LIMIT 100
                """,
                (cid, today),
            ).fetchall()
        predictions = []
        for row in rows:
            try:
                exp = datetime.strptime(row["expiry_date"][:10], "%Y-%m-%d")
                days_left = (exp - datetime.strptime(today, "%Y-%m-%d")).days
                risk = "high" if days_left <= 7 else "medium" if days_left <= 30 else "low"
            except ValueError:
                days_left = None
                risk = "unknown"
            predictions.append({**dict(row), "days_left": days_left, "risk": risk})
        return jsonify({"predictions": predictions})

    # ── IoT device ping ───────────────────────────────────────────────────────
    @enterprise_bp.post("/iot/devices/<device_id>/telemetry")
    def iot_telemetry(device_id: str):
        from backend.server import get_db
        from backend.app.platform.events.bus import publish_event

        data = request.get_json(silent=True) or {}
        get_db().execute(
            """
            INSERT INTO iot_telemetry (id, device_id, payload_json, received_at)
            VALUES (?, ?, ?, ?)
            """,
            (f"iot-{uuid.uuid4().hex[:10]}", device_id, json.dumps(data), _now_iso()),
        )
        get_db().commit()
        publish_event("iot.telemetry", data.get("company_id"), {"device_id": device_id, "payload": data})
        return jsonify({"ok": True})

    # ── Live dashboard (extends operations snapshot) ──────────────────────────
    @enterprise_bp.get("/dashboard/live")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def dashboard_live():
        from backend.app.db.connection import get_read_connection
        from backend.server import utc_now
        from backend.app.platform.events.bus import list_recent_events

        cid = _company_id()
        today_prefix = utc_now().strftime("%Y-%m-%d")
        with get_read_connection() as db:
            on_site_row = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM (
                    SELECT al.worker_id, al.direction
                    FROM access_logs al
                    JOIN workers w ON w.id = al.worker_id
                    WHERE w.company_id = ? AND w.deleted_at IS NULL AND al.timestamp LIKE ?
                      AND al.timestamp = (
                          SELECT MAX(al2.timestamp) FROM access_logs al2
                          WHERE al2.worker_id = al.worker_id AND al2.timestamp LIKE ?
                      )
                ) latest
                WHERE latest.direction = 'check-in'
                """,
                (cid, f"{today_prefix}%", f"{today_prefix}%"),
            ).fetchone()
        events = list_recent_events(cid, limit=30)
        return jsonify(
            {
                "date": today_prefix,
                "workersOnSite": int((on_site_row["c"] if on_site_row else 0) or 0),
                "recent_events": events,
            }
        )

    flask_app.register_blueprint(enterprise_bp, url_prefix="/api")
