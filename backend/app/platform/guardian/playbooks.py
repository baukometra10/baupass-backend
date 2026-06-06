"""Safe auto-remediation playbooks for Platform Guardian."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

_playbook_last_run: dict[str, float] = {}


def remediation_enabled() -> bool:
    return os.getenv("BAUPASS_GUARDIAN_REMEDIATION", "1").strip().lower() not in {"0", "false", "no"}


def remediation_cooldown_seconds() -> int:
    return max(60, int(os.getenv("BAUPASS_GUARDIAN_REMEDIATION_COOLDOWN_SECONDS", "300")))


def reset_playbook_state_for_tests() -> None:
    _playbook_last_run.clear()


def _can_run(playbook_id: str) -> bool:
    last = _playbook_last_run.get(playbook_id, 0.0)
    return (time.time() - last) >= remediation_cooldown_seconds()


def _mark_run(playbook_id: str) -> None:
    _playbook_last_run[playbook_id] = time.time()


def cleanup_expired_sessions(db, *, force: bool = False) -> dict[str, Any]:
    if not force and not _can_run("expired_sessions"):
        return {"id": "expired_sessions", "skipped": "cooldown"}
    try:
        from backend.server import now_iso

        now = now_iso()
        admin_deleted = int(db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,)).rowcount or 0)
        worker_deleted = int(db.execute("DELETE FROM worker_app_sessions WHERE expires_at < ?", (now,)).rowcount or 0)
        token_deleted = int(db.execute("DELETE FROM worker_app_tokens WHERE expires_at < ?", (now,)).rowcount or 0)
        db.commit()
        _mark_run("expired_sessions")
        total = admin_deleted + worker_deleted + token_deleted
        return {
            "id": "expired_sessions",
            "ok": True,
            "deleted": {
                "adminSessions": admin_deleted,
                "workerSessions": worker_deleted,
                "workerTokens": token_deleted,
                "total": total,
            },
        }
    except Exception as exc:
        return {"id": "expired_sessions", "ok": False, "error": str(exc)[:200]}


def ack_stale_info_alerts(db, *, after_hours: int = 24, force: bool = False) -> dict[str, Any]:
    if not force and not _can_run("stale_info_alerts"):
        return {"id": "stale_info_alerts", "skipped": "cooldown"}
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, after_hours))).strftime("%Y-%m-%dT%H:%M:%SZ")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
        rows = db.execute(
            """
            SELECT id FROM system_alerts
            WHERE resolved_at IS NULL
              AND LOWER(COALESCE(severity, '')) = 'info'
              AND created_at < ?
            LIMIT 200
            """,
            (cutoff,),
        ).fetchall()
        count = 0
        for row in rows:
            db.execute(
                "UPDATE system_alerts SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
                (now, row["id"]),
            )
            count += 1
        if count:
            db.commit()
        _mark_run("stale_info_alerts")
        return {"id": "stale_info_alerts", "ok": True, "resolved": count}
    except Exception as exc:
        return {"id": "stale_info_alerts", "ok": False, "error": str(exc)[:200]}


def trigger_worker_session_cleanup(*, force: bool = False) -> dict[str, Any]:
    if not force and not _can_run("worker_session_cleanup"):
        return {"id": "worker_session_cleanup", "skipped": "cooldown"}
    try:
        from backend.server import run_worker_session_cleanup_cycle_once

        result = run_worker_session_cleanup_cycle_once() or {}
        _mark_run("worker_session_cleanup")
        return {"id": "worker_session_cleanup", **result}
    except Exception as exc:
        return {"id": "worker_session_cleanup", "ok": False, "error": str(exc)[:200]}


def trigger_invoice_retry(*, force: bool = False) -> dict[str, Any]:
    if not force and not _can_run("invoice_retry"):
        return {"id": "invoice_retry", "skipped": "cooldown"}
    try:
        from backend.server import run_invoice_retry_cycle_once

        result = run_invoice_retry_cycle_once() or {}
        _mark_run("invoice_retry")
        return {"id": "invoice_retry", **result}
    except Exception as exc:
        return {"id": "invoice_retry", "ok": False, "error": str(exc)[:200]}


def run_playbooks(
    db,
    *,
    db_ok: bool,
    status: str,
    workers_degraded: bool,
    dead_letter_total: int = 0,
    force: bool = False,
) -> dict[str, Any]:
    if not remediation_enabled() and not force:
        return {"enabled": False, "actions": []}

    actions: list[dict[str, Any]] = []
    if not db_ok:
        return {"enabled": True, "actions": actions, "skipped": "database_unhealthy"}

    actions.append(cleanup_expired_sessions(db, force=force))
    actions.append(trigger_worker_session_cleanup(force=force))

    should_retry_invoices = force or (
        not workers_degraded
        and (
            status in {"degraded", "down"}
            or dead_letter_total > 0
        )
    )
    if should_retry_invoices and not workers_degraded:
        actions.append(trigger_invoice_retry(force=force))

    if force or status in {"degraded", "down"}:
        actions.append(ack_stale_info_alerts(db, force=force))

    applied = [a for a in actions if a.get("ok") and not a.get("skipped")]
    return {"enabled": True, "actions": actions, "appliedCount": len(applied), "forced": force}
