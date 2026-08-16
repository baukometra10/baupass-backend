"""Safe auto-remediation playbooks for Platform Guardian."""
from __future__ import annotations

import gc
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

_playbook_last_run: dict[str, float] = {}
_urgent_mode: bool = False


def remediation_enabled() -> bool:
    from .env import guardian_flag

    return guardian_flag("REMEDIATION", "1")


def remediation_cooldown_seconds(*, urgent: bool | None = None) -> int:
    from .env import guardian_int

    use_urgent = _urgent_mode if urgent is None else bool(urgent)
    if use_urgent:
        # Crash-prevention mode: heal again within ~45s while degraded/down.
        return guardian_int("REMEDIATION_URGENT_COOLDOWN_SECONDS", 45, minimum=15)
    return guardian_int("REMEDIATION_COOLDOWN_SECONDS", 90, minimum=30)


def reset_playbook_state_for_tests() -> None:
    global _urgent_mode
    _playbook_last_run.clear()
    _urgent_mode = False


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


def retry_missing_api_routes(*, failed_probes: list[str] | None = None, force: bool = False) -> dict[str, Any]:
    """Re-mount critical domain/platform blueprints when registry/API probes fail."""
    failed = set(failed_probes or [])
    needs = force or bool(
        failed.intersection(
            {
                "api_route_registry",
                "api_companies",
                "api_ops_command",
                "api_daily_brief",
                "api_live_map",
                "api_docs_inbox",
                "api_admin_overview",
                "api_billing_pricing",
                "api",
                "ready",
            }
        )
    )
    if not needs:
        return {"id": "retry_api_routes", "skipped": "no_api_probe_failure"}
    if not force and not _can_run("retry_api_routes"):
        return {"id": "retry_api_routes", "skipped": "cooldown"}
    try:
        from backend.server import (
            _ensure_billing_v2_routes,
            _ensure_critical_api_routes,
            _ensure_platform_workforce_routes,
            _retry_failed_domain_blueprints,
        )

        _retry_failed_domain_blueprints()
        _ensure_critical_api_routes()
        _ensure_platform_workforce_routes()
        _ensure_billing_v2_routes()
        _mark_run("retry_api_routes")
        return {"id": "retry_api_routes", "ok": True, "forced": force, "triggers": sorted(failed)}
    except Exception as exc:
        return {"id": "retry_api_routes", "ok": False, "error": str(exc)[:200]}


def sqlite_stabilize(db, *, force: bool = False) -> dict[str, Any]:
    """WAL checkpoint + quick integrity — prevents disk/WAL growth crashes."""
    if not force and not _can_run("sqlite_stabilize"):
        return {"id": "sqlite_stabilize", "skipped": "cooldown"}
    try:
        backend = ""
        try:
            row = db.execute("PRAGMA database_list").fetchone()
            file_path = str((row["file"] if row and "file" in row.keys() else "") or "")
            backend = "sqlite" if file_path.endswith(".db") or file_path == "" or ":memory:" in file_path else "other"
        except Exception:
            backend = "unknown"
        if backend == "other":
            return {"id": "sqlite_stabilize", "skipped": "not_sqlite"}

        checkpoint = None
        try:
            checkpoint = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        except Exception:
            try:
                checkpoint = db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            except Exception:
                checkpoint = None

        quick = "ok"
        try:
            qrow = db.execute("PRAGMA quick_check(1)").fetchone()
            quick = str(qrow[0] if qrow is not None else "ok")
        except Exception as exc:
            quick = f"error:{exc}"[:80]

        try:
            db.execute("PRAGMA optimize")
        except Exception:
            pass
        try:
            db.commit()
        except Exception:
            pass

        _mark_run("sqlite_stabilize")
        ok = str(quick).lower() in {"ok", "ok."}
        return {
            "id": "sqlite_stabilize",
            "ok": ok,
            "quickCheck": quick,
            "checkpoint": list(checkpoint) if checkpoint is not None else None,
        }
    except Exception as exc:
        return {"id": "sqlite_stabilize", "ok": False, "error": str(exc)[:200]}


def memory_pressure_relief(*, force: bool = False) -> dict[str, Any]:
    """Release unreferenced objects before memory pressure becomes a crash."""
    if not force and not _can_run("memory_pressure_relief"):
        return {"id": "memory_pressure_relief", "skipped": "cooldown"}
    try:
        collected = int(gc.collect() or 0)
        # Second pass catches cyclic leftovers after first sweep.
        collected += int(gc.collect(2) or 0)
        _mark_run("memory_pressure_relief")
        return {"id": "memory_pressure_relief", "ok": True, "collected": collected}
    except Exception as exc:
        return {"id": "memory_pressure_relief", "ok": False, "error": str(exc)[:200]}


def trim_task_dead_letter(*, dead_letter_total: int = 0, force: bool = False) -> dict[str, Any]:
    """Keep Redis DLQ bounded so queue/memory spikes cannot take the app down."""
    threshold = 80
    try:
        from .env import guardian_int

        threshold = guardian_int("DLQ_TRIM_THRESHOLD", 80, minimum=20)
    except Exception:
        pass
    if not force and int(dead_letter_total or 0) < threshold:
        return {"id": "trim_task_dead_letter", "skipped": "below_threshold", "total": dead_letter_total}
    if not force and not _can_run("trim_task_dead_letter"):
        return {"id": "trim_task_dead_letter", "skipped": "cooldown"}
    try:
        from backend.app import tasks as task_mod

        _redis_conn = getattr(task_mod, "_redis_conn", None)
        if _redis_conn is None:
            return {"id": "trim_task_dead_letter", "skipped": "redis_unavailable"}
        key = "baupass:dlq:events"
        before = int(_redis_conn.llen(key) or 0)
        keep = 120
        if before > keep:
            # Keep newest events only.
            _redis_conn.ltrim(key, 0, keep - 1)
        after = int(_redis_conn.llen(key) or 0)
        _mark_run("trim_task_dead_letter")
        return {
            "id": "trim_task_dead_letter",
            "ok": True,
            "before": before,
            "after": after,
            "trimmed": max(0, before - after),
        }
    except Exception as exc:
        return {"id": "trim_task_dead_letter", "ok": False, "error": str(exc)[:200]}


def harden_critical_routes(*, force: bool = False) -> dict[str, Any]:
    """Preventive remount of critical routes before customers hit 404/500 gaps."""
    if not force and not _can_run("harden_critical_routes"):
        return {"id": "harden_critical_routes", "skipped": "cooldown"}
    try:
        from backend.server import (
            _ensure_billing_v2_routes,
            _ensure_critical_api_routes,
            _ensure_platform_workforce_routes,
        )

        _ensure_critical_api_routes()
        _ensure_platform_workforce_routes()
        _ensure_billing_v2_routes()
        _mark_run("harden_critical_routes")
        return {"id": "harden_critical_routes", "ok": True, "forced": force}
    except Exception as exc:
        return {"id": "harden_critical_routes", "ok": False, "error": str(exc)[:200]}


def run_playbooks(
    db,
    *,
    db_ok: bool,
    status: str,
    workers_degraded: bool,
    dead_letter_total: int = 0,
    failed_probes: list[str] | None = None,
    force: bool = False,
    urgent: bool | None = None,
) -> dict[str, Any]:
    global _urgent_mode
    if not remediation_enabled() and not force:
        return {"enabled": False, "actions": []}

    failed_probes = list(failed_probes or [])
    status_l = str(status or "unknown").lower()
    bad = status_l in {"degraded", "down"}
    use_urgent = bool(urgent) if urgent is not None else (force or bad or bool(failed_probes))
    prev_urgent = _urgent_mode
    _urgent_mode = use_urgent
    actions: list[dict[str, Any]] = []

    try:
        if not db_ok:
            actions.append(recover_sqlite_storage(db_ok=False, force=force or True))
            actions.append(memory_pressure_relief(force=True))
            applied = [a for a in actions if a.get("ok") and not a.get("skipped")]
            return {
                "enabled": True,
                "actions": actions,
                "appliedCount": len(applied),
                "forced": force,
                "urgent": use_urgent,
                "mode": "crash_prevention",
                "skipped": "database_unhealthy",
            }

        # 1) Stop user-facing breakage first.
        if force or bad or failed_probes:
            actions.append(
                retry_missing_api_routes(
                    failed_probes=failed_probes,
                    force=force or bad,
                )
            )
        else:
            actions.append(harden_critical_routes(force=force))

        # 2) Stabilize storage / memory before secondary jobs.
        actions.append(sqlite_stabilize(db, force=force or bad))
        actions.append(memory_pressure_relief(force=force or bad))
        actions.append(trim_task_dead_letter(dead_letter_total=dead_letter_total, force=force or bad))

        # 3) Housekeeping that prevents auth/session storms.
        actions.append(cleanup_expired_sessions(db, force=force))
        actions.append(trigger_worker_session_cleanup(force=force))
        actions.append(lift_expired_rate_limit_bans(db, force=force))
        actions.append(trigger_access_maintenance(db, force=force))

        should_retry_invoices = force or (
            not workers_degraded
            and (bad or dead_letter_total > 0)
        )
        if should_retry_invoices and not workers_degraded:
            actions.append(trigger_invoice_retry(force=force))

        if status_l == "ok" or force:
            actions.append(resolve_guardian_status_alerts(db, status=status_l, force=force))

        if force or bad:
            actions.append(ack_stale_info_alerts(db, force=force))
            actions.append(ack_stale_warning_alerts(db, force=force))

        if failed_probes and (force or bad):
            actions.append(recover_sqlite_storage(db_ok=db_ok, force=force or bad))

        applied = [a for a in actions if a.get("ok") and not a.get("skipped")]
        return {
            "enabled": True,
            "actions": actions,
            "appliedCount": len(applied),
            "forced": force,
            "urgent": use_urgent,
            "mode": "crash_prevention" if use_urgent else "preventive",
        }
    finally:
        _urgent_mode = prev_urgent

