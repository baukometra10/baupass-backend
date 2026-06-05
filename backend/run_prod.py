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

from backend.app.config import ProductionConfig  # noqa: E402
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


def _validate_production_config() -> None:
    env_name = str(os.getenv("BAUPASS_ENV", "")).strip().lower()
    if not env_name:
        env_name = "production"
        os.environ["BAUPASS_ENV"] = env_name
        print("[baupass] BAUPASS_ENV not set; defaulting to production", flush=True)

    if env_name not in {"production", "prod"}:
        return
    try:
        ProductionConfig.validate()
    except Exception as exc:
        print(f"[baupass] PRODUCTION CONFIG VALIDATION FAILED: {exc}", flush=True)
        sys.exit(1)


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
    _validate_production_config()
    run_dunning_on_boot = str(os.getenv("BAUPASS_RUN_DUNNING_ON_BOOT", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    run_backup_on_boot = str(os.getenv("BAUPASS_BACKUP_ON_BOOT", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    # init_db() wird bereits beim Import von backend.server ausgeführt.

    if str(os.getenv("BAUPASS_SEED_DEMO_ENTERPRISE", "0")).strip().lower() in {"1", "true", "yes", "on"}:
        try:
            from backend.ops.seed_demo_enterprise import seed_demo_enterprise

            with app.app_context():
                result = seed_demo_enterprise()
            print(f"[baupass] Demo enterprise seed: {result}", flush=True)
        except Exception as exc:
            print(f"[baupass] WARNING: demo enterprise seed skipped: {exc}", flush=True)
    is_testing = str(os.getenv("BAUPASS_ENV", "")).strip().lower() == "testing"
    if not is_testing and not (os.getenv("SENTRY_DSN") or "").strip():
        print("[baupass] TIP: Set SENTRY_DSN for production error tracking", flush=True)
    if os.getenv("BAUPASS_PLATFORM_ENABLED", "1").strip().lower() not in {"0", "false", "no"}:
        print(f"[baupass] Prometheus metrics available at http://{HOST}:{PORT}/metrics", flush=True)
        print("[baupass] Observability status at /observability/status", flush=True)
    if not is_testing:
        audit_key = (os.getenv("BAUPASS_AUDIT_SIGNING_KEY") or "").strip()
        if not audit_key or audit_key == "dev-insecure-audit-key":
            print("[baupass] SECURITY WARNING: BAUPASS_AUDIT_SIGNING_KEY not set — audit trail uses insecure default key!", flush=True)
        gate_key = (os.getenv("BAUPASS_GATE_API_KEY") or "").strip()
        if not gate_key:
            print("[baupass] SECURITY WARNING: BAUPASS_GATE_API_KEY not set — gate tap API is unauthenticated!", flush=True)
        recovery_secret = (os.getenv("BAUPASS_RECOVERY_SECRET") or "").strip()
        if not recovery_secret:
            print("[baupass] SECURITY WARNING: BAUPASS_RECOVERY_SECRET not set — emergency recovery endpoint is disabled.", flush=True)
        field_enc_key = (os.getenv("BAUPASS_FIELD_ENCRYPTION_KEY") or "").strip()
        if not field_enc_key:
            print("[baupass] TIP: Set BAUPASS_FIELD_ENCRYPTION_KEY for field-level document encryption.", flush=True)
    try:
        from backend.app.db.runtime import postgres_runtime_enabled
        from backend.app.database import postgres_preflight

        if postgres_runtime_enabled():
            try:
                from backend.app.db.pg_bootstrap import ensure_postgres_bootstrap

                ensure_postgres_bootstrap()
            except Exception as exc:
                print(f"[baupass] WARNING: PostgreSQL bootstrap failed: {exc}", flush=True)
            pf = postgres_preflight()
            print(f"[baupass] PostgreSQL preflight: {pf.get('status')}", flush=True)
        else:
            from backend.app.runtime_bootstrap import apply_sqlite_migrations
            from backend.server import DB_PATH

            applied = apply_sqlite_migrations(Path(DB_PATH))
            if applied:
                print(f"[baupass] Migrations on boot: {', '.join(applied)}", flush=True)
    except Exception as exc:
        print(f"[baupass] WARNING: database prep on boot failed: {exc}", flush=True)
    data_dir = Path("/data")
    if data_dir.exists():
        print(
            f"[baupass] /data volume: exists=True writable={os.access(data_dir, os.W_OK)}",
            flush=True,
        )
    else:
        print("[baupass] /data volume: exists=False (not mounted in this container)", flush=True)

    dunning_result = {
        "remindersSent": 0,
        "reminderFailures": 0,
        "overdueUpdated": 0,
    }
    suspended = []

    try:
        with app.app_context():
            db = get_db()
            if run_dunning_on_boot:
                # Optional on-boot dunning; disabled by default to avoid delaying bind/readiness on platforms like Railway.
                try:
                    dunning_result = run_invoice_dunning_cycle(db)
                except Exception as exc:
                    print(f"[baupass] WARNING: on-boot dunning skipped: {exc}", flush=True)
            try:
                suspended = check_and_apply_overdue_suspensions(db)
            except Exception as exc:
                print(f"[baupass] WARNING: overdue suspension check skipped: {exc}", flush=True)
    except Exception as exc:
        print(f"[baupass] CRITICAL: Post-initialization tasks failed: {exc}", flush=True)

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
    
    # Backup only if explicitly requested or on persistent volumes with data
    if run_backup_on_boot and db_info.get("persistent") and int(db_info.get("workersActive") or 0) > 0:
        try:
            backup_path, backup_meta = create_sqlite_database_backup()
            print(
                f"[baupass] Startup DB backup: {backup_path} ({backup_meta.get('sizeBytes', 0)} bytes)",
                flush=True,
            )
        except Exception as backup_exc:
            print(f"[baupass] WARNING: Startup DB backup failed: {backup_exc}", flush=True)

    archive_on_boot = str(os.getenv("BAUPASS_ARCHIVE_ACCESS_LOGS_ON_BOOT", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if archive_on_boot:
        try:
            with app.app_context():
                from backend.app.tasks.access_logs_archive import archive_access_logs

                archive_result = archive_access_logs(get_db())
                print(f"[baupass] Access log archive: {archive_result}", flush=True)
        except Exception as archive_exc:
            print(f"[baupass] WARNING: access log archive skipped: {archive_exc}", flush=True)

    try:
        from backend.app.db.runtime import postgres_runtime_enabled

        if postgres_runtime_enabled() and str(os.getenv("BAUPASS_PG_DR_SNAPSHOT_ON_BOOT", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
        }:
            from backend.ops.postgres_dr_snapshot import table_counts

            snap = {"ok": True, "tableCounts": table_counts()}
            print(f"[baupass] PostgreSQL DR snapshot counts: {snap.get('tableCounts')}", flush=True)
    except Exception as pg_dr_exc:
        print(f"[baupass] WARNING: PG DR snapshot skipped: {pg_dr_exc}", flush=True)

    try:
        from backend.app.core.cloud_profile import get_cloud_profile

        profile = get_cloud_profile()
        print(
            f"[baupass] Cloud: provider={profile.get('provider')} "
            f"region={profile.get('region')} env={profile.get('environment')} "
            f"strategy={profile.get('regionStrategy')} active={profile.get('activeRegions')}",
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
        schedule_archive = str(os.getenv("BAUPASS_SCHEDULE_ACCESS_ARCHIVE", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if schedule_archive and task_queues_ready():
            try:
                from backend.app.tasks import enqueue
                from backend.app.tasks.maintenance_jobs import run_access_log_archive

                enqueue("scheduled", run_access_log_archive)
                print("[baupass] Scheduled access_log archive job enqueued", flush=True)
            except Exception as sched_exc:
                print(f"[baupass] WARNING: schedule archive skipped: {sched_exc}", flush=True)
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
