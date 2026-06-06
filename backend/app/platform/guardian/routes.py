"""Platform Guardian API."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

guardian_bp = Blueprint("platform_guardian", __name__)


def register_guardian_blueprint(flask_app) -> None:
    from backend.server import get_db, require_auth, require_roles

    from .history import get_history
    from .playbooks import run_playbooks
    from .runner import collect_ops_summary, get_guardian_snapshot, run_guardian_cycle

    @guardian_bp.get("/guardian/status")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def guardian_status():
        snapshot = get_guardian_snapshot()
        if not snapshot.get("timestamp"):
            host = (request.host or "").strip()
            public_url = request.url_root.rstrip("/")
            snapshot = run_guardian_cycle(current_app._get_current_object(), host=host, public_url=public_url)
        try:
            snapshot["ops"] = collect_ops_summary(get_db())
        except Exception:
            snapshot["ops"] = {}
        return jsonify(snapshot), 200

    @guardian_bp.get("/guardian/history")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def guardian_history():
        limit = min(20, max(1, int(request.args.get("limit", "20"))))
        return jsonify({"history": get_history(limit)}), 200

    @guardian_bp.get("/guardian/ops-summary")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def guardian_ops_summary():
        return jsonify(collect_ops_summary(get_db())), 200

    @guardian_bp.post("/guardian/check")
    @require_auth
    @require_roles("superadmin")
    def guardian_check_now():
        host = (request.host or "").strip()
        public_url = request.url_root.rstrip("/")
        snapshot = run_guardian_cycle(
            current_app._get_current_object(),
            host=host,
            public_url=public_url,
            force_alert=True,
        )
        return jsonify(snapshot), 200

    @guardian_bp.post("/guardian/remediate")
    @require_auth
    @require_roles("superadmin")
    def guardian_remediate_now():
        from backend.app.database import get_database_health
        from backend.app.tasks import get_dead_letter_stats

        from .runner import _collect_worker_check

        host = (request.host or "").strip()
        public_url = request.url_root.rstrip("/")
        db = get_db()
        db_health = get_database_health()
        db_ok = db_health.get("status") == "ok"
        worker_check = _collect_worker_check()
        snapshot = get_guardian_snapshot()
        status = str(snapshot.get("status") or "degraded")
        dead_letter_total = 0
        try:
            dead_letter_total = int((get_dead_letter_stats() or {}).get("total_events") or 0)
        except Exception:
            pass
        remediation = run_playbooks(
            db,
            db_ok=db_ok,
            status=status,
            workers_degraded=bool(worker_check.get("degraded")),
            dead_letter_total=dead_letter_total,
            force=True,
        )
        refreshed = run_guardian_cycle(
            current_app._get_current_object(),
            host=host,
            public_url=public_url,
        )
        refreshed["manualRemediation"] = remediation
        return jsonify(refreshed), 200

    flask_app.register_blueprint(guardian_bp, url_prefix="/api")
