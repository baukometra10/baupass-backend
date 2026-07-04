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


def lift_expired_rate_limit_bans(db, *, force: bool = False) -> dict[str, Any]:
    if not force and not _can_run("lift_expired_bans"):
        return {"id": "lift_expired_bans", "skipped": "cooldown"}
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
        lifted = int(
            db.execute(
                """
                UPDATE rate_limit_bans
                SET lifted_at = ?
                WHERE lifted_at IS NULL AND expires_at <= ?
                """,
                (now, now),
            ).rowcount
            or 0
        )
        if lifted:
            db.commit()
        _mark_run("lift_expired_bans")
        return {"id": "lift_expired_bans", "ok": True, "lifted": lifted}
    except Exception as exc:
        return {"id": "lift_expired_bans", "ok": False, "error": str(exc)[:200]}


def resolve_guardian_status_alerts(db, *, status: str, force: bool = False) -> dict[str, Any]:
    if status != "ok" and not force:
        return {"id": "resolve_guardian_alerts", "skipped": "status_not_ok"}
    if not force and not _can_run("resolve_guardian_alerts"):
        return {"id": "resolve_guardian_alerts", "skipped": "cooldown"}
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
        resolved = int(
            db.execute(
                """
                UPDATE system_alerts
                SET resolved_at = ?
                WHERE resolved_at IS NULL
                  AND code IN ('platform_guardian_status', 'guardian_login_spike')
                """,
                (now,),
            ).rowcount
            or 0
        )
        if resolved:
            db.commit()
        _mark_run("resolve_guardian_alerts")
        return {"id": "resolve_guardian_alerts", "ok": True, "resolved": resolved}
    except Exception as exc:
        return {"id": "resolve_guardian_alerts", "ok": False, "error": str(exc)[:200]}


def trigger_access_maintenance(db, *, force: bool = False) -> dict[str, Any]:
    if not force and not _can_run("access_maintenance"):
        return {"id": "access_maintenance", "skipped": "cooldown"}
    try:
        from backend.server import run_access_maintenance_if_due

        run_access_maintenance_if_due(db)
        _mark_run("access_maintenance")
        return {"id": "access_maintenance", "ok": True}
    except Exception as exc:
        return {"id": "access_maintenance", "ok": False, "error": str(exc)[:200]}


def recover_sqlite_storage(*, db_ok: bool, force: bool = False) -> dict[str, Any]:
    if db_ok and not force:
        return {"id": "sqlite_recover", "skipped": "db_ok"}
    if not force and not _can_run("sqlite_recover"):
        return {"id": "sqlite_recover", "skipped": "cooldown"}
    try:
        import os

        from backend.app.core.sqlite_pragmas import recover_sqlite_disk_io

        db_path_raw = os.getenv("BAUPASS_DB_PATH", "").strip()
        if not db_path_raw:
            try:
                from backend.server import DB_PATH

                db_path_raw = str(DB_PATH)
            except Exception:
                return {"id": "sqlite_recover", "skipped": "no_db_path"}
        if not db_path_raw.lower().endswith(".db"):
            return {"id": "sqlite_recover", "skipped": "not_sqlite"}
        from pathlib import Path

        recovered = recover_sqlite_disk_io(Path(db_path_raw))
        _mark_run("sqlite_recover")
        return {"id": "sqlite_recover", "ok": True, "recovered": recovered}
    except Exception as exc:
        return {"id": "sqlite_recover", "ok": False, "error": str(exc)[:200]}


def ack_stale_warning_alerts(db, *, after_hours: int = 48, force: bool = False) -> dict[str, Any]:
    if not force and not _can_run("stale_warning_alerts"):
        return {"id": "stale_warning_alerts", "skipped": "cooldown"}
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, after_hours))).strftime("%Y-%m-%dT%H:%M:%SZ")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
        rows = db.execute(
            """
            SELECT id FROM system_alerts
            WHERE resolved_at IS NULL
              AND LOWER(COALESCE(severity, '')) = 'warning'
              AND created_at < ?
            LIMIT 100
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
        _mark_run("stale_warning_alerts")
        return {"id": "stale_warning_alerts", "ok": True, "resolved": count}
    except Exception as exc:
        return {"id": "stale_warning_alerts", "ok": False, "error": str(exc)[:200]}


def run_playbooks(
    db,
    *,
    db_ok: bool,
    status: str,
    workers_degraded: bool,
    dead_letter_total: int = 0,
    failed_probes: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if not remediation_enabled() and not force:
        return {"enabled": False, "actions": []}

    failed_probes = list(failed_probes or [])
    actions: list[dict[str, Any]] = []

    if not db_ok:
        actions.append(recover_sqlite_storage(db_ok=False, force=force))
        applied = [a for a in actions if a.get("ok") and not a.get("skipped")]
        return {"enabled": True, "actions": actions, "appliedCount": len(applied), "forced": force, "skipped": "database_unhealthy"}

    actions.append(cleanup_expired_sessions(db, force=force))
    actions.append(trigger_worker_session_cleanup(force=force))
    actions.append(lift_expired_rate_limit_bans(db, force=force))
    actions.append(trigger_access_maintenance(db, force=force))

    should_retry_invoices = force or (
        not workers_degraded
        and (
            status in {"degraded", "down"}
            or dead_letter_total > 0
        )
    )
    if should_retry_invoices and not workers_degraded:
        actions.append(trigger_invoice_retry(force=force))

    if status == "ok" or force:
        actions.append(resolve_guardian_status_alerts(db, status=status, force=force))

    if force or status in {"degraded", "down"}:
        actions.append(ack_stale_info_alerts(db, force=force))
        actions.append(ack_stale_warning_alerts(db, force=force))

    if failed_probes and (force or status in {"degraded", "down"}):
        actions.append(recover_sqlite_storage(db_ok=db_ok, force=force))

    applied = [a for a in actions if a.get("ok") and not a.get("skipped")]
    return {"enabled": True, "actions": actions, "appliedCount": len(applied), "forced": force}
