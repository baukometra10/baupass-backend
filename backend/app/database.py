"""
BauPass – Database Layer
=========================
مسؤوليات هذا الملف:
  1. إدارة اتصالات SQLite بشكل آمن (WAL, busy_timeout, row_factory)
  2. نظام migrations بسيط وآمن (append-only, rollback-safe)
  3. Tenant-aware connection wrapper
  4. Context manager للـ transactions

الانتقال إلى PostgreSQL:
  عند الجاهزية، استبدل get_connection() بـ psycopg2/asyncpg
  مع الحفاظ على نفس الواجهة (MigrationRunner, TenantAwareDB, etc.)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from flask import g

logger = logging.getLogger("baupass.database")

# ── Thread-local storage للاتصالات ───────────────────────────────────────────
_local = threading.local()

# ── Migration lock (يمنع تشغيل migrations بالتوازي) ─────────────────────────
_migration_lock = threading.Lock()

# ── PostgreSQL pool globals (transition mode) ───────────────────────────────
_pg_pool = None
_pg_pool_lock = threading.Lock()
_pg_read_pool = None
_pg_read_pool_lock = threading.Lock()


# =============================================================================
# Connection Management
# =============================================================================

def get_db_path() -> Path:
    """يُحدد مسار قاعدة البيانات بالأولوية: env var > Railway /data > default."""
    from flask import current_app

    explicit = current_app.config.get("SQLITE_PATH", "").strip()
    if explicit and explicit != ":memory:":
        return Path(explicit).expanduser()

    railway_data = Path("/data")
    if railway_data.is_dir() and railway_data.stat().st_mode & 0o200:
        return railway_data / "baupass.db"

    base = Path(__file__).resolve().parent.parent.parent
    return base / "backend" / "baupass.db"


def _resolve_database_url(config: Optional[dict[str, Any]] = None) -> str:
    if config and config.get("DATABASE_URL"):
        return str(config.get("DATABASE_URL", "")).strip()
    return os.getenv("DATABASE_URL", "").strip()


def _resolve_read_replica_url(config: Optional[dict[str, Any]] = None) -> str:
    if config and config.get("DATABASE_READ_REPLICA_URL"):
        return str(config.get("DATABASE_READ_REPLICA_URL", "")).strip()
    return os.getenv("DATABASE_READ_REPLICA_URL", "").strip()


def is_postgres_configured(config: Optional[dict[str, Any]] = None) -> bool:
    url = _resolve_database_url(config)
    return url.startswith("postgres://") or url.startswith("postgresql://")


def is_postgres_replica_configured(config: Optional[dict[str, Any]] = None) -> bool:
    url = _resolve_read_replica_url(config)
    return url.startswith("postgres://") or url.startswith("postgresql://")


def init_postgres_pool(config: Optional[dict[str, Any]] = None) -> bool:
    """
    Initializes PostgreSQL connection pool if DATABASE_URL points to postgres.
    Safe to call multiple times.
    """
    global _pg_pool

    if _pg_pool is not None:
        return True

    database_url = _resolve_database_url(config)
    if not (database_url.startswith("postgres://") or database_url.startswith("postgresql://")):
        return False

    try:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        min_size = int((config or {}).get("DB_POOL_MIN_SIZE", os.getenv("DB_POOL_MIN_SIZE", "2")))
        max_size = int((config or {}).get("DB_POOL_MAX_SIZE", os.getenv("DB_POOL_MAX_SIZE", "20")))
        timeout = int((config or {}).get("DB_POOL_TIMEOUT_SECONDS", os.getenv("DB_POOL_TIMEOUT_SECONDS", "10")))

        with _pg_pool_lock:
            if _pg_pool is not None:
                return True

            pool = ConnectionPool(
                conninfo=database_url,
                min_size=max(1, min_size),
                max_size=max(max_size, min_size),
                timeout=max(3, timeout),
                kwargs={
                    "autocommit": False,
                    "row_factory": dict_row,
                },
            )
            pool.wait(timeout=max(3, timeout))
            _pg_pool = pool

        logger.info(
            "PostgreSQL pool initialized (min=%s max=%s timeout=%ss)",
            min_size,
            max_size,
            timeout,
        )
        return True
    except Exception as exc:
        logger.error("Failed to initialize PostgreSQL pool: %s", exc)
        return False


def init_postgres_read_pool(config: Optional[dict[str, Any]] = None) -> bool:
    """
    Initializes PostgreSQL read-replica connection pool.
    Falls back to primary pool when replica URL is not configured.
    """
    global _pg_read_pool

    if _pg_read_pool is not None:
        return True

    replica_url = _resolve_read_replica_url(config)
    if not (replica_url.startswith("postgres://") or replica_url.startswith("postgresql://")):
        return init_postgres_pool(config)

    try:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        min_size = int((config or {}).get("DB_READ_POOL_MIN_SIZE", os.getenv("DB_READ_POOL_MIN_SIZE", "2")))
        max_size = int((config or {}).get("DB_READ_POOL_MAX_SIZE", os.getenv("DB_READ_POOL_MAX_SIZE", "16")))
        timeout = int((config or {}).get("DB_POOL_TIMEOUT_SECONDS", os.getenv("DB_POOL_TIMEOUT_SECONDS", "10")))

        with _pg_read_pool_lock:
            if _pg_read_pool is not None:
                return True
            pool = ConnectionPool(
                conninfo=replica_url,
                min_size=max(1, min_size),
                max_size=max(max_size, min_size),
                timeout=max(3, timeout),
                kwargs={
                    "autocommit": True,
                    "row_factory": dict_row,
                },
            )
            pool.wait(timeout=max(3, timeout))
            _pg_read_pool = pool
        logger.info(
            "PostgreSQL read-replica pool initialized (min=%s max=%s timeout=%ss)",
            min_size,
            max_size,
            timeout,
        )
        return True
    except Exception as exc:
        logger.error("Failed to initialize PostgreSQL read-replica pool: %s", exc)
        return False


def close_postgres_pool() -> None:
    global _pg_pool, _pg_read_pool
    with _pg_pool_lock:
        if _pg_pool is not None:
            try:
                _pg_pool.close()
            finally:
                _pg_pool = None
    with _pg_read_pool_lock:
        if _pg_read_pool is not None:
            try:
                _pg_read_pool.close()
            finally:
                _pg_read_pool = None


def get_postgres_pool_stats() -> dict[str, Any]:
    if _pg_pool is None:
        return {"status": "not_initialized"}
    try:
        stats = _pg_pool.get_stats() or {}
        return {"status": "ok", **stats}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def get_postgres_read_pool_stats() -> dict[str, Any]:
    if _pg_read_pool is None:
        if is_postgres_replica_configured():
            return {"status": "not_initialized", "replica_configured": True}
        return {"status": "disabled", "replica_configured": False}
    try:
        stats = _pg_read_pool.get_stats() or {}
        return {"status": "ok", "replica_configured": True, **stats}
    except Exception as exc:
        return {"status": "error", "replica_configured": True, "error": str(exc)}


@contextmanager
def postgres_connection() -> Generator[Any, None, None]:
    """Returns a pooled PostgreSQL connection."""
    if _pg_pool is None:
        raise RuntimeError("PostgreSQL pool is not initialized")
    with _pg_pool.connection() as conn:
        yield conn


@contextmanager
def postgres_read_connection() -> Generator[Any, None, None]:
    """
    Returns a read-only pooled PostgreSQL connection.
    Uses replica when configured, otherwise primary.
    """
    if _pg_read_pool is None:
        init_postgres_read_pool()
    if _pg_read_pool is not None:
        with _pg_read_pool.connection() as conn:
            yield conn
        return
    with postgres_connection() as conn:
        yield conn


@contextmanager
def postgres_transaction() -> Generator[Any, None, None]:
    """Runs statements in a PostgreSQL transaction with automatic rollback."""
    with postgres_connection() as conn:
        with conn.transaction():
            yield conn


def postgres_preflight(config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Connectivity check for PostgreSQL runtime path."""
    if not is_postgres_configured(config):
        return {"enabled": False, "status": "skipped", "reason": "DATABASE_URL not postgres"}

    started = time.monotonic()
    ok = init_postgres_pool(config)
    if not ok:
        return {"enabled": True, "status": "error", "error": "pool_init_failed"}

    try:
        with postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "enabled": True,
            "status": "ok",
            "duration_ms": duration_ms,
            "pool": get_postgres_pool_stats(),
        }
    except Exception as exc:
        return {"enabled": True, "status": "error", "error": str(exc)}


def postgres_replica_preflight(config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if not is_postgres_replica_configured(config):
        return {"enabled": False, "status": "skipped", "reason": "DATABASE_READ_REPLICA_URL not set"}

    started = time.monotonic()
    ok = init_postgres_read_pool(config)
    if not ok:
        return {"enabled": True, "status": "error", "error": "read_pool_init_failed"}
    try:
        with postgres_read_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "enabled": True,
            "status": "ok",
            "duration_ms": duration_ms,
            "pool": get_postgres_read_pool_stats(),
        }
    except Exception as exc:
        return {"enabled": True, "status": "error", "error": str(exc)}


def get_database_health(config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Unified database health check for readiness and observability."""
    if is_postgres_configured(config):
        return {
            "backend": "postgres",
            **postgres_preflight(config),
            "read_replica": postgres_replica_preflight(config),
        }

    try:
        db_path = get_db_path()
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.execute("SELECT 1").fetchone()
            db_size = db_path.stat().st_size if db_path.exists() else 0
            companies_total = 0
            companies_active = 0
            try:
                companies_total = int(conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0])
                companies_active = int(
                    conn.execute("SELECT COUNT(*) FROM companies WHERE deleted_at IS NULL").fetchone()[0]
                )
            except sqlite3.Error:
                pass
        return {
            "backend": "sqlite",
            "enabled": True,
            "status": "ok",
            "path": str(db_path),
            "size_bytes": db_size,
            "companies_total": companies_total,
            "companies_active": companies_active,
        }
    except Exception as exc:
        return {"backend": "sqlite", "enabled": True, "status": "error", "error": str(exc)}


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    يُعيد اتصال SQLite من request context (يُخزَّن في flask.g).
    يُهيئ WAL mode و PRAGMA المثلى في أول اتصال.
    """
    if "_db" not in g:
        path = db_path or get_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(path), timeout=60.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # تهيئة PRAGMA للأداء والأمان
        conn.executescript("""
            PRAGMA journal_mode = WAL;
            PRAGMA synchronous   = NORMAL;
            PRAGMA busy_timeout  = 60000;
            PRAGMA cache_size    = -64000;
            PRAGMA mmap_size     = 268435456;
            PRAGMA foreign_keys  = ON;
            PRAGMA temp_store    = MEMORY;
        """)

        g._db = conn

    return g._db


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager للـ transactions الصريحة.

    مثال:
        with transaction(get_connection()) as db:
            db.execute("INSERT INTO ...")
            db.execute("UPDATE ...")
        # يُعمل COMMIT تلقائياً عند الخروج
        # يُعمل ROLLBACK إذا حدث استثناء
    """
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# =============================================================================
# Migration System
# =============================================================================

MIGRATIONS_TABLE = "_baupass_migrations"

_BOOTSTRAP_SQL = f"""
CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    version     TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    checksum    TEXT NOT NULL,
    applied_at  TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    rolled_back INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_{MIGRATIONS_TABLE}_version ON {MIGRATIONS_TABLE}(version);
"""


class Migration:
    """تمثيل migration واحد."""

    def __init__(
        self,
        version: str,        # مثل: "001", "002", "20240101_001"
        name: str,           # وصف قصير
        up_sql: str,         # SQL للتطبيق
        down_sql: str = "",  # SQL للـ rollback (اختياري لكن مهم)
    ):
        self.version = version
        self.name = name
        self.up_sql = up_sql.strip()
        self.down_sql = down_sql.strip()
        self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        """بصمة SHA-256 للـ migration لاكتشاف التعديل غير المقصود."""
        content = f"{self.version}:{self.name}:{self.up_sql}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class MigrationRunner:
    """
    يُشغّل migrations بترتيب ويتحقق من سلامتها.

    الضمانات:
    - كل migration يُطبَّق مرة واحدة فقط (idempotent)
    - إذا تغير محتوى migration مطبَّق → خطأ صريح (checksum mismatch)
    - كل migration يُسجَّل في جدول {MIGRATIONS_TABLE} مع timestamp ومدة التنفيذ
    - يمكن rollback للـ migration الأخير إذا كان down_sql موجوداً
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._bootstrap()

    def _bootstrap(self) -> None:
        """إنشاء جدول المتابعة إذا لم يكن موجوداً."""
        self.conn.executescript(_BOOTSTRAP_SQL)
        self.conn.commit()

    def applied_versions(self) -> set[str]:
        rows = self.conn.execute(
            f"SELECT version FROM {MIGRATIONS_TABLE} WHERE rolled_back = 0"
        ).fetchall()
        return {row["version"] for row in rows}

    def verify_checksums(self, migrations: list[Migration]) -> None:
        """يتحقق أن migrations المطبَّقة لم تتغير."""
        applied = {
            row["version"]: row["checksum"]
            for row in self.conn.execute(
                f"SELECT version, checksum FROM {MIGRATIONS_TABLE} WHERE rolled_back = 0"
            ).fetchall()
        }
        for m in migrations:
            if m.version in applied and applied[m.version] != m.checksum:
                raise RuntimeError(
                    f"Migration {m.version} ({m.name}) checksum mismatch!\n"
                    f"  Expected: {applied[m.version]}\n"
                    f"  Got:      {m.checksum}\n"
                    f"Do NOT modify applied migrations. Create a new migration instead."
                )

    def run(self, migrations: list[Migration], dry_run: bool = False) -> list[str]:
        """
        يُطبّق كل migrations جديدة بالترتيب.

        Returns: قائمة بـ versions التي طُبِّقت في هذه الجلسة.
        """
        with _migration_lock:
            self.verify_checksums(migrations)
            applied = self.applied_versions()
            pending = [m for m in migrations if m.version not in applied]

            if not pending:
                logger.debug("Database migrations: up to date (%d total)", len(migrations))
                return []

            logger.info(
                "Database migrations: %d pending of %d total",
                len(pending), len(migrations),
            )

            executed = []
            for migration in sorted(pending, key=lambda m: (int(m.version), m.name)):
                if dry_run:
                    logger.info("  [dry-run] Would apply: %s – %s", migration.version, migration.name)
                    executed.append(migration.version)
                    continue

                start = time.monotonic()
                logger.info("  Applying migration %s: %s", migration.version, migration.name)

                try:
                    self.conn.executescript(migration.up_sql)
                except sqlite3.Error as exc:
                    raise RuntimeError(
                        f"Migration {migration.version} ({migration.name}) failed:\n{exc}\n"
                        f"SQL:\n{migration.up_sql}"
                    ) from exc

                duration_ms = int((time.monotonic() - start) * 1000)

                self.conn.execute(
                    f"INSERT INTO {MIGRATIONS_TABLE} "
                    f"(version, name, checksum, applied_at, duration_ms) "
                    f"VALUES (?, ?, ?, ?, ?)",
                    (
                        migration.version,
                        migration.name,
                        migration.checksum,
                        datetime.now(timezone.utc).isoformat(),
                        duration_ms,
                    ),
                )
                self.conn.commit()
                executed.append(migration.version)
                logger.info(
                    "  ✓ Migration %s applied in %dms",
                    migration.version, duration_ms,
                )

            return executed

    def rollback_last(self) -> Optional[str]:
        """
        يُعيد آخر migration (إذا كان down_sql موجوداً).
        تحذير: استخدم هذا بحذر في الإنتاج.
        """
        row = self.conn.execute(
            f"SELECT * FROM {MIGRATIONS_TABLE} WHERE rolled_back = 0 "
            f"ORDER BY id DESC LIMIT 1"
        ).fetchone()

        if not row:
            logger.info("No migrations to roll back.")
            return None

        version = row["version"]
        logger.warning("Rolling back migration: %s", version)

        self.conn.execute(
            f"UPDATE {MIGRATIONS_TABLE} SET rolled_back = 1 WHERE version = ?",
            (version,),
        )
        self.conn.commit()
        logger.warning("Rolled back migration %s (down_sql must be applied manually)", version)
        return version

    def status(self) -> list[dict]:
        """يُعيد حالة جميع migrations المطبَّقة."""
        rows = self.conn.execute(
            f"SELECT * FROM {MIGRATIONS_TABLE} ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]


# =============================================================================
# Tenant-Aware Database Wrapper
# =============================================================================

class TenantDB:
    """
    Wrapper حول sqlite3.Connection يُضيف:
    - tenant_id مرتبط بكل اتصال
    - تحقق تلقائي أن الـ query لا تعمل بدون company_id في جداول متعددة المستأجرين
    - audit trail تلقائي للعمليات الحساسة

    الاستخدام:
        db = TenantDB(get_connection(), company_id=g.current_user["company_id"])
        workers = db.execute_for_tenant("SELECT * FROM workers WHERE company_id = ?")
        # company_id يُضاف تلقائياً كـ parameter أول
    """

    # الجداول التي تحتوي بيانات multi-tenant ويجب تقييدها
    TENANT_TABLES = frozenset({
        "workers", "companies", "access_logs", "documents",
        "invoices", "work_schedules", "gates", "visitors",
        "audit_log", "worker_passes", "dunning_records",
    })

    def __init__(self, conn: sqlite3.Connection, company_id: int):
        if not company_id or company_id <= 0:
            raise ValueError("TenantDB requires a valid company_id > 0")
        self._conn = conn
        self.company_id = company_id

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """تنفيذ query عادي مع الحفاظ على context."""
        return self._conn.execute(sql, params)

    def execute_for_tenant(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        تنفيذ query مع إضافة company_id تلقائياً كـ parameter أول.
        يُستخدم مع SQL التي تحتوي ? الأول لـ company_id.

        مثال:
            rows = db.execute_for_tenant(
                "SELECT * FROM workers WHERE company_id = ?",
            )
            # يُصبح: SELECT * FROM workers WHERE company_id = 42
        """
        return self._conn.execute(sql, (self.company_id, *params))

    def fetchone_for_tenant(
        self, sql: str, params: tuple = (), id_value: Any = None
    ) -> Optional[sqlite3.Row]:
        """
        يُعيد سجلاً واحداً مع التحقق من tenant ownership.

        مثال:
            worker = db.fetchone_for_tenant(
                "SELECT * FROM workers WHERE id = ? AND company_id = ?",
                id_value=worker_id,
            )
        """
        if id_value is not None:
            return self._conn.execute(
                sql, (id_value, self.company_id, *params)
            ).fetchone()
        return self._conn.execute(sql, (self.company_id, *params)).fetchone()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    @contextmanager
    def transaction(self) -> Generator["TenantDB", None, None]:
        """Context manager للـ transactions مع الـ tenant context."""
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            yield self
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
