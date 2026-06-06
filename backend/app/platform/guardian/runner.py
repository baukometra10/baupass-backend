"""Platform Guardian — watches health and raises ops alerts."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from flask import Flask

from backend.app.database import get_database_health
from backend.app.health.platform_probe import collect_platform_health
from backend.app.tasks import get_worker_heartbeat_stats

from .history import append_history, get_history
from .notify import maybe_notify_guardian
from .playbooks import run_playbooks
from .security import maybe_raise_security_alert, scan_security

_last_snapshot: dict[str, Any] = {
    "status": "unknown",
    "enabled": True,
    "timestamp": None,
}
_previous_status: str = "unknown"
_last_run_at: float = 0.0


def guardian_enabled() -> bool:
    return os.getenv("BAUPASS_GUARDIAN_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def guardian_interval_seconds() -> int:
    return max(30, int(os.getenv("BAUPASS_GUARDIAN_INTERVAL_SECONDS", "60")))


def get_guardian_snapshot() -> dict[str, Any]:
    return dict(_last_snapshot)


def reset_guardian_state_for_tests() -> None:
    global _previous_status, _last_run_at
    _last_snapshot.clear()
    _last_snapshot.update({"status": "unknown", "enabled": True, "timestamp": None})
    _previous_status = "unknown"
    _last_run_at = 0.0


def _collect_worker_check() -> dict[str, Any]:
    try:
        workers = get_worker_heartbeat_stats()
        rq_modes_enabled = any(
            str(os.getenv(name, "thread")).strip().lower() == "rq"
            for name in (
                "BAUPASS_INVOICE_RETRY_MODE",
                "BAUPASS_WORKER_SESSION_CLEANUP_MODE",
                "BAUPASS_DAILY_JOBS_MODE",
            )
        )
        degraded = rq_modes_enabled and int(workers.get("active", 0)) < 1
        return {"workers": workers, "rqModesEnabled": rq_modes_enabled, "degraded": degraded}
    except Exception as exc:
        return {"workers": {"status": "unavailable"}, "error": str(exc), "degraded": True}


def _merge_status(platform_status: str, *, db_ok: bool, workers_degraded: bool) -> str:
    status = str(platform_status or "ok").lower()
    if status == "down":
        return "down"
    if not db_ok or workers_degraded or status == "degraded":
        return "degraded"
    return "ok"


def run_guardian_cycle(app: Flask, *, host: str = "", public_url: str = "", force_alert: bool = False) -> dict[str, Any]:
    global _previous_status, _last_run_at

    started = time.monotonic()
    platform = collect_platform_health(app, host=host, public_url=public_url)
    worker_check = _collect_worker_check()
    db_health = get_database_health()
    db_ok = db_health.get("status") == "ok"

    failed_probes = [p["id"] for p in platform.get("probes") or [] if not p.get("ok")]
    status = _merge_status(platform.get("status"), db_ok=db_ok, workers_degraded=bool(worker_check.get("degraded")))

    dead_letter_total = 0
    try:
        from backend.app.tasks import get_dead_letter_stats

        dead_letter_total = int((get_dead_letter_stats() or {}).get("total_events") or 0)
    except Exception:
        pass

    remediation: dict[str, Any] = {"enabled": False, "actions": []}
    security: dict[str, Any] = {"enabled": False, "elevated": False, "severity": "ok"}
    security_alert: dict[str, Any] = {"sent": 0, "skipped": "not_run"}

    if db_ok:
        try:
            from backend.server import get_db

            db = get_db()
            remediation = run_playbooks(
                db,
                db_ok=db_ok,
                status=status,
                workers_degraded=bool(worker_check.get("degraded")),
                dead_letter_total=dead_letter_total,
            )
            security = scan_security(db)
            security_alert = maybe_raise_security_alert(db, security)
        except Exception as exc:
            remediation = {"enabled": True, "error": str(exc)[:200], "actions": []}
            security = {"enabled": True, "error": str(exc)[:200], "elevated": False, "severity": "ok"}

    snapshot: dict[str, Any] = {
        "status": status,
        "ready": bool(platform.get("ready")) and db_ok,
        "enabled": guardian_enabled(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "durationMs": int((time.monotonic() - started) * 1000),
        "cloud": platform.get("cloud") or {},
        "database": db_health,
        "probes": platform.get("probes") or [],
        "failedProbes": failed_probes,
        "workers": worker_check.get("workers") or {},
        "workersDegraded": bool(worker_check.get("degraded")),
        "deadLetterTotal": dead_letter_total,
        "remediation": remediation,
        "security": security,
        "securityAlert": security_alert,
        "previousStatus": _previous_status,
    }

    notify_result = maybe_notify_guardian(
        snapshot,
        previous_status=_previous_status,
        force=force_alert,
    )
    snapshot["alert"] = notify_result

    if status in {"degraded", "down"}:
        try:
            from backend.server import create_system_alert, get_db

            create_system_alert(
                get_db(),
                code="platform_guardian_status",
                severity="critical" if status == "down" else "warning",
                message=f"Platform Guardian: {status.upper()}",
                details={
                    "failedProbes": failed_probes,
                    "workersDegraded": snapshot["workersDegraded"],
                    "host": (snapshot.get("cloud") or {}).get("host"),
                },
                dedup_minutes=max(5, guardian_interval_seconds() // 60),
            )
        except Exception:
            pass
    elif _previous_status in {"degraded", "down"} and status == "ok":
        try:
            from backend.server import create_system_alert, get_db

            create_system_alert(
                get_db(),
                code="platform_guardian_recovered",
                severity="info",
                message="Platform Guardian: wieder OK",
                details={"host": (snapshot.get("cloud") or {}).get("host")},
                dedup_minutes=30,
            )
        except Exception:
            pass

    _previous_status = status
    _last_run_at = time.time()
    _last_snapshot.clear()
    _last_snapshot.update(snapshot)
    append_history(snapshot)
    snapshot["ok"] = status == "ok"
    return snapshot


def get_guardian_history(limit: int = 20) -> list[dict[str, Any]]:
    return get_history(limit)


def collect_ops_summary(db) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "invoiceDeadLetters": 0,
        "criticalInvoiceRetries": 0,
        "queueDeadLetterEvents": 0,
        "activeWorkers": 0,
    }
    try:
        from backend.server import get_critical_invoice_retry_summary, get_invoice_dead_letters

        summary["invoiceDeadLetters"] = len(get_invoice_dead_letters(db) or [])
        retry_summary = get_critical_invoice_retry_summary(db) or {}
        summary["criticalInvoiceRetries"] = int(retry_summary.get("criticalCount") or 0)
    except Exception:
        pass
    try:
        from backend.app.tasks import get_dead_letter_stats, get_worker_heartbeat_stats

        dl = get_dead_letter_stats() or {}
        summary["queueDeadLetterEvents"] = int(dl.get("total_events") or 0)
        workers = get_worker_heartbeat_stats() or {}
        summary["activeWorkers"] = int(workers.get("active") or 0)
    except Exception:
        pass
    return summary
