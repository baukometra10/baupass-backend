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


def _ensure_postgres_bootstrap() -> None:
    """If PG runtime is enabled and key tables are missing, auto-migrate from SQLite."""
    auto = str(os.getenv("BAUPASS_PG_AUTO_BOOTSTRAP", "1")).strip().lower() in {"1", "true", "yes", "on"}
    if not auto:
        return
    from backend.app.db.runtime import postgres_runtime_enabled

    if not postgres_runtime_enabled():
        return
    from backend.app.database import init_postgres_pool, postgres_connection

    init_postgres_pool()
    with postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('system_alerts', 'invoices', 'workers', 'companies')
                """
            )
            existing = {row[0] for row in cur.fetchall()}
    required = {"system_alerts", "invoices", "workers", "companies"}
    if required.issubset(existing):
        print("[baupass] PostgreSQL bootstrap: schema already present", flush=True)
        return

    source = os.getenv("BAUPASS_PG_BOOTSTRAP_SQLITE_PATH", os.getenv("BAUPASS_DB_PATH", "/data/baupass.db"))
    source_path = Path(source).expanduser()
    if not source_path.exists():
        raise RuntimeError(
            f"PostgreSQL tables missing ({sorted(required - existing)}), "
            f"but bootstrap SQLite source not found: {source_path}"
        )
    from backend.ops.sqlite_to_postgres import migrate_sqlite_to_postgres

    result = migrate_sqlite_to_postgres(source_path, truncate=False, schema_only=False)
    print(
        f"[baupass] PostgreSQL bootstrap completed from {source_path} "
        f"(tables={result.get('tables')}, rows={result.get('rows')})",
        flush=True,
    )


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
    try:
        from backend.app.db.runtime import postgres_runtime_enabled
        from backend.app.database import postgres_preflight

        if postgres_runtime_enabled():
            _ensure_postgres_bootstrap()
            pf = postgres_preflight()
            print(f"[baupass] PostgreSQL preflight: {pf.get('status')}", flush=True)
        else:
            from backend.app.runtime_bootstrap import apply_sqlite_migrations
            from backend.server import DB_PATH

            applied = apply_sqlite_migrations(Path(DB_PATH))
            if applied:
                print(f"[baupass] Migrations on boot: {', '.join(applied)}", flush=True)
    except Exception as exc:
        print(f"[baupass] WARNING: migrations on boot failed: {exc}", flush=True)
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

    try:
        from backend.app.core.cloud_profile import get_cloud_profile

        profile = get_cloud_profile()
        print(
            f"[baupass] Cloud: provider={profile.get('provider')} "
            f"region={profile.get('region')} env={profile.get('environment')}",
            flush=True,
        )
    except Exception:
        pass
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
        from backend.app.extensions import get_redis
        from backend.app.runtime_bootstrap import resolve_background_job_mode
        from backend.app.tasks import get_queue_stats, task_queues_ready

        redis = get_redis()
        if redis:
            try:
                redis.ping()
                print("[baupass] Redis: connected", flush=True)
            except Exception as redis_exc:
                print(f"[baupass] Redis: ping failed ({redis_exc})", flush=True)
        else:
            print("[baupass] Redis: not configured (rate limits use in-memory fallback)", flush=True)

        if task_queues_ready():
            try:
                stats = get_queue_stats()
                print(f"[baupass] RQ queues: {stats}", flush=True)
            except Exception:
                print("[baupass] RQ queues: ready", flush=True)
        else:
            print("[baupass] RQ queues: not ready", flush=True)

        rq_modes = {
            "daily_jobs": resolve_background_job_mode("BAUPASS_DAILY_JOBS_MODE"),
            "session_cleanup": resolve_background_job_mode("BAUPASS_WORKER_SESSION_CLEANUP_MODE"),
            "invoice_retry": resolve_background_job_mode("BAUPASS_INVOICE_RETRY_MODE"),
            "dunning": resolve_background_job_mode("BAUPASS_DUNNING_MODE"),
        }
        print(f"[baupass] Background job modes: {rq_modes}", flush=True)
        if any(mode == "rq" for mode in rq_modes.values()):
            print(
                "[baupass] RQ modes active — run worker service: "
                "python -m backend.app.tasks.worker",
                flush=True,
            )
    except Exception as boot_exc:
        print(f"[baupass] Runtime queue check skipped: {boot_exc}", flush=True)
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
