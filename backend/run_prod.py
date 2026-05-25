import socket
import sys
import os
import logging
from pathlib import Path

from waitress import serve

# Ensure project root is on sys.path when started from backend/ (Docker, Railway).
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.server import (  # noqa: E402
    app,
    check_and_apply_overdue_suspensions,
    create_sqlite_database_backup,
    get_database_runtime_info,
    get_db,
    get_runtime_diagnostics,
    init_db,
    run_invoice_dunning_cycle,
)


HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))


def _int_env(name, default, minimum):
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, value)


WAITRESS_THREADS = _int_env("BAUPASS_WAITRESS_THREADS", 16, 8)
WAITRESS_CONNECTION_LIMIT = _int_env("BAUPASS_WAITRESS_CONNECTION_LIMIT", 400, 100)
WAITRESS_CHANNEL_TIMEOUT = _int_env("BAUPASS_WAITRESS_CHANNEL_TIMEOUT", 120, 30)
WAITRESS_CLEANUP_INTERVAL = _int_env("BAUPASS_WAITRESS_CLEANUP_INTERVAL", 30, 5)
SHOW_WAITRESS_QUEUE_WARNINGS = str(os.getenv("BAUPASS_WAITRESS_QUEUE_WARNINGS", "0")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def port_is_listening(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


if __name__ == "__main__":
    run_dunning_on_boot = str(os.getenv("BAUPASS_RUN_DUNNING_ON_BOOT", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    init_db()
    data_dir = Path("/data")
    if data_dir.exists():
        print(
            f"[baupass] /data volume: exists=True writable={os.access(data_dir, os.W_OK)}",
            flush=True,
        )
    else:
        print("[baupass] /data volume: exists=False (not mounted in this container)", flush=True)
    with app.app_context():
        db = get_db()
        dunning_result = {
            "remindersSent": 0,
            "reminderFailures": 0,
            "overdueUpdated": 0,
        }
        if run_dunning_on_boot:
            # Optional on-boot dunning; disabled by default to avoid delaying bind/readiness on platforms like Railway.
            dunning_result = run_invoice_dunning_cycle(db)
        suspended = check_and_apply_overdue_suspensions(db)
    if dunning_result.get("remindersSent") or dunning_result.get("reminderFailures") or dunning_result.get("overdueUpdated"):
        print(
            "[baupass] Dunning cycle: "
            f"sent={dunning_result.get('remindersSent', 0)}, "
            f"failed={dunning_result.get('reminderFailures', 0)}, "
            f"overdue_updated={dunning_result.get('overdueUpdated', 0)}"
        )
    if suspended:
        print(f"[baupass] Auto-suspended {len(suspended)} company/ies due to overdue invoices")
    db_info = get_database_runtime_info()
    print(
        "[baupass] Database: "
        f"path={db_info.get('path')}, "
        f"persistent={db_info.get('persistent')}, "
        f"workers={db_info.get('workersActive')}, "
        f"companies={db_info.get('companiesActive')}, "
        f"sizeBytes={db_info.get('sizeBytes')}",
        flush=True,
    )
    backup_on_boot = str(os.getenv("BAUPASS_BACKUP_ON_BOOT", "1")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if backup_on_boot and db_info.get("persistent") and int(db_info.get("workersActive") or 0) > 0:
        try:
            backup_path, backup_meta = create_sqlite_database_backup()
            print(
                f"[baupass] Startup DB backup: {backup_path} ({backup_meta.get('sizeBytes', 0)} bytes)",
                flush=True,
            )
        except Exception as backup_exc:
            print(f"[baupass] WARNING: Startup DB backup failed: {backup_exc}", flush=True)

    diagnostics = get_runtime_diagnostics()
    warnings = diagnostics.get("warnings", [])
    print(f"[baupass] Runtime-Check: {len(warnings)} Warnung(en)")
    resend_configured = bool(diagnostics.get("resendConfigured"))
    resend_source = str(diagnostics.get("resendKeySource") or "")
    if resend_configured:
        print(f"[baupass] Resend: configured (source={resend_source or 'unknown'})")
    else:
        print("[baupass] Resend: NOT configured")
    for warning in warnings:
        print(f"[baupass][warn] {warning['code']}: {warning['message']}")
    try:
        from backend.app.runtime_bootstrap import resolve_background_job_mode

        rq_modes = [
            resolve_background_job_mode("BAUPASS_DAILY_JOBS_MODE"),
            resolve_background_job_mode("BAUPASS_WORKER_SESSION_CLEANUP_MODE"),
            resolve_background_job_mode("BAUPASS_INVOICE_RETRY_MODE"),
            resolve_background_job_mode("BAUPASS_DUNNING_MODE"),
        ]
        if any(mode == "rq" for mode in rq_modes):
            print(
                "[baupass] RQ background modes active — start a worker process: "
                "python -m backend.app.tasks.worker"
            )
    except Exception:
        pass
    if not SHOW_WAITRESS_QUEUE_WARNINGS:
        # Queue depth warnings are noisy under short bursts and do not always indicate a real issue.
        logging.getLogger("waitress.queue").setLevel(logging.ERROR)
    print(
        "[baupass] Waitress: "
        f"threads={WAITRESS_THREADS}, "
        f"connection_limit={WAITRESS_CONNECTION_LIMIT}, "
        f"channel_timeout={WAITRESS_CHANNEL_TIMEOUT}s"
    )
    serve(
        app,
        host=HOST,
        port=PORT,
        threads=WAITRESS_THREADS,
        connection_limit=WAITRESS_CONNECTION_LIMIT,
        channel_timeout=WAITRESS_CHANNEL_TIMEOUT,
        cleanup_interval=WAITRESS_CLEANUP_INTERVAL,
    )
