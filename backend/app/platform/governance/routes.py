"""Governance & compliance APIs (Phase B)."""
from __future__ import annotations

import json
import secrets

from flask import Blueprint, g, jsonify, request

governance_bp = Blueprint("governance", __name__)


def register_governance_blueprint(flask_app) -> None:
    from backend.server import get_db, now_iso, require_auth, require_roles, row_to_dict
    from backend.app.platform.rbac.enforcement import has_permission

    def _company_id() -> str:
        user = g.current_user
        payload = request.get_json(silent=True) or {}
        if user.get("role") == "superadmin":
            return str(request.args.get("company_id") or payload.get("companyId") or "").strip()
        return str(user.get("company_id") or "")

    def _require_governance_perm():
        db = get_db()
        if not has_permission(db, g.current_user, "governance.retention") and g.current_user.get("role") != "superadmin":
            return jsonify({"error": "forbidden", "required": "governance.retention"}), 403
        return None

    @governance_bp.get("/governance/retention")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def get_retention():
        denied = _require_governance_perm()
        if denied:
            return denied
        cid = _company_id()
        if not cid:
            return jsonify({"error": "missing_company_id"}), 400
        db = get_db()
        row = db.execute(
            "SELECT * FROM company_retention_policies WHERE company_id = ?",
            (cid,),
        ).fetchone()
        if not row:
            return jsonify(
                {
                    "companyId": cid,
                    "accessLogDays": 2555,
                    "auditLogDays": 2555,
                    "documentDays": 365,
                    "workerProfileDays": 2555,
                    "defaults": True,
                }
            )
        return jsonify(
            {
                "companyId": cid,
                "accessLogDays": int(row["access_log_days"]),
                "auditLogDays": int(row["audit_log_days"]),
                "documentDays": int(row["document_days"]),
                "workerProfileDays": int(row["worker_profile_days"]),
                "updatedAt": row["updated_at"],
                "defaults": False,
            }
        )

    @governance_bp.put("/governance/retention")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def put_retention():
        denied = _require_governance_perm()
        if denied:
            return denied
        cid = _company_id()
        if not cid:
            return jsonify({"error": "missing_company_id"}), 400
        payload = request.get_json(silent=True) or {}
        db = get_db()
        now = now_iso()
        db.execute(
            """
            INSERT INTO company_retention_policies
            (company_id, access_log_days, audit_log_days, document_days, worker_profile_days, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id) DO UPDATE SET
                access_log_days = excluded.access_log_days,
                audit_log_days = excluded.audit_log_days,
                document_days = excluded.document_days,
                worker_profile_days = excluded.worker_profile_days,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            (
                cid,
                int(payload.get("accessLogDays", 2555)),
                int(payload.get("auditLogDays", 2555)),
                int(payload.get("documentDays", 365)),
                int(payload.get("workerProfileDays", 2555)),
                now,
                g.current_user.get("id"),
            ),
        )
        db.commit()
        return jsonify({"ok": True, "companyId": cid, "updatedAt": now})

    @governance_bp.get("/governance/legal-holds")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def list_legal_holds():
        denied = _require_governance_perm()
        if denied:
            return denied
        cid = _company_id()
        if not cid:
            return jsonify({"error": "missing_company_id"}), 400
        db = get_db()
        rows = db.execute(
            """
            SELECT id, target_type, target_id, reason, active, created_at, released_at
            FROM legal_holds WHERE company_id = ? ORDER BY created_at DESC LIMIT 200
            """,
            (cid,),
        ).fetchall()
        return jsonify({"items": [dict(r) for r in rows]})

    @governance_bp.post("/governance/legal-holds")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def create_legal_hold():
        denied = _require_governance_perm()
        if denied:
            return denied
        cid = _company_id()
        payload = request.get_json(silent=True) or {}
        if not cid:
            cid = str(payload.get("companyId") or g.current_user.get("company_id") or "")
        if not cid:
            return jsonify({"error": "missing_company_id"}), 400
        target_type = str(payload.get("targetType") or "company").strip()
        target_id = str(payload.get("targetId") or cid).strip()
        reason = str(payload.get("reason") or "Legal hold")[:2000]
        hold_id = f"lh-{secrets.token_hex(8)}"
        now = now_iso()
        db = get_db()
        db.execute(
            """
            INSERT INTO legal_holds (id, company_id, target_type, target_id, reason, active, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (hold_id, cid, target_type, target_id, reason, g.current_user.get("id"), now),
        )
        db.commit()
        return jsonify({"ok": True, "id": hold_id, "companyId": cid})

    @governance_bp.post("/governance/legal-holds/<hold_id>/release")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def release_legal_hold(hold_id):
        denied = _require_governance_perm()
        if denied:
            return denied
        db = get_db()
        row = db.execute("SELECT company_id FROM legal_holds WHERE id = ?", (hold_id,)).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404
        if g.current_user.get("role") != "superadmin" and str(row["company_id"]) != str(g.current_user.get("company_id") or ""):
            return jsonify({"error": "forbidden"}), 403
        db.execute(
            "UPDATE legal_holds SET active = 0, released_at = ? WHERE id = ?",
            (now_iso(), hold_id),
        )
        db.commit()
        return jsonify({"ok": True, "id": hold_id})

    @governance_bp.post("/governance/export")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def governance_export():
        from backend.app.platform.rbac.enforcement import has_permission

        db = get_db()
        if not has_permission(db, g.current_user, "reports.export") and g.current_user.get("role") != "superadmin":
            return jsonify({"error": "forbidden"}), 403
        cid = _company_id()
        if not cid:
            return jsonify({"error": "missing_company_id"}), 400
        workers = db.execute(
            "SELECT id, first_name, last_name, status, site, valid_until FROM workers WHERE company_id = ? AND deleted_at IS NULL LIMIT 5000",
            (cid,),
        ).fetchall()
        audits = db.execute(
            "SELECT id, event_type, message, created_at FROM audit_logs WHERE company_id = ? ORDER BY created_at DESC LIMIT 2000",
            (cid,),
        ).fetchall()
        holds = db.execute(
            "SELECT * FROM legal_holds WHERE company_id = ? AND active = 1",
            (cid,),
        ).fetchall()
        retention = db.execute(
            "SELECT * FROM company_retention_policies WHERE company_id = ?",
            (cid,),
        ).fetchone()
        return jsonify(
            {
                "ok": True,
                "companyId": cid,
                "exportedAt": now_iso(),
                "workers": [dict(w) for w in workers],
                "auditLogs": [dict(a) for a in audits],
                "legalHolds": [dict(h) for h in holds],
                "retention": dict(retention) if retention else None,
            }
        )

    @governance_bp.get("/governance/scheduled-reports")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def list_scheduled_reports():
        cid = _company_id()
        if not cid:
            return jsonify({"error": "missing_company_id"}), 400
        rows = get_db().execute(
            "SELECT * FROM scheduled_report_jobs WHERE company_id = ? ORDER BY created_at DESC",
            (cid,),
        ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            try:
                d["recipients"] = json.loads(d.pop("recipients_json", "[]") or "[]")
            except json.JSONDecodeError:
                d["recipients"] = []
            items.append(d)
        return jsonify({"items": items})

    @governance_bp.post("/governance/scheduled-reports")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def create_scheduled_report():
        payload = request.get_json(silent=True) or {}
        cid = _company_id() or str(payload.get("companyId") or g.current_user.get("company_id") or "")
        if not cid:
            return jsonify({"error": "missing_company_id"}), 400
        job_id = f"srj-{secrets.token_hex(8)}"
        now = now_iso()
        recipients = payload.get("recipients") or []
        db = get_db()
        db.execute(
            """
            INSERT INTO scheduled_report_jobs
            (id, company_id, report_type, recipients_json, local_hour, timezone, enabled, attach_datev, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                cid,
                str(payload.get("reportType") or "executive"),
                json.dumps(recipients),
                int(payload.get("localHour", 8)),
                str(payload.get("timezone") or "Europe/Berlin"),
                1 if payload.get("enabled", True) else 0,
                1 if payload.get("attachDatev") else 0,
                now,
                now,
            ),
        )
        db.commit()
        return jsonify({"ok": True, "id": job_id})

    flask_app.register_blueprint(governance_bp, url_prefix="/api")
