"""
BauPass – Configuration Management
====================================
بيئات:
  - DevelopmentConfig : للتطوير المحلي
  - TestingConfig     : للاختبارات الآلية (in-memory SQLite)
  - ProductionConfig  : للإنتاج

جميع القيم الحساسة تُقرأ من متغيرات البيئة فقط.
لا توجد قيم حساسة مكتوبة مباشرة في الكود.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # workspace root


def _env_flag_enabled(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def _require_env(key: str) -> str:
    """يُجبر على وجود متغير البيئة في الإنتاج. يرفع خطأ صريحاً إذا كان مفقوداً."""
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(
            f"[BauPass] Missing required environment variable: {key}\n"
            f"Set it in your .env file or deployment configuration."
        )
    return value


class BaseConfig:
    # ── Flask Core ────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.getenv("BAUPASS_SECRET_KEY", "")
    DEBUG: bool = False
    TESTING: bool = False

    # ── Database ──────────────────────────────────────────────────────────────
    # تحديد مسار SQLite أو DATABASE_URL لـ PostgreSQL مستقبلاً
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()
    DATABASE_READ_REPLICA_URL: str = os.getenv("DATABASE_READ_REPLICA_URL", "").strip()
    SQLITE_PATH: str = os.getenv("BAUPASS_DB_PATH", "").strip()
    DB_POOL_MIN_SIZE: int = int(os.getenv("DB_POOL_MIN_SIZE", "2"))
    DB_POOL_MAX_SIZE: int = int(os.getenv("DB_POOL_MAX_SIZE", "20"))
    DB_POOL_TIMEOUT_SECONDS: int = int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "10"))

    # SQLite tuning
    SQLITE_WAL_MODE: bool = True
    SQLITE_BUSY_TIMEOUT_MS: int = 60_000
    SQLITE_CACHE_SIZE_KB: int = 64_000  # 64 MB page cache
    SQLITE_MMAP_SIZE_BYTES: int = 256 * 1024 * 1024  # 256 MB

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_MAX_CONNECTIONS: int = 20
    REDIS_SOCKET_TIMEOUT: float = 3.0
    REDIS_RETRY_ON_TIMEOUT: bool = True
    # When True, Redis failures are non-fatal: rate limiting and task queues
    # fall back to in-memory / synchronous implementations automatically.
    REDIS_OPTIONAL: bool = _env_flag_enabled("BAUPASS_REDIS_OPTIONAL", "1")

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    # المفتاح يُبنى في Redis: ratelimit:{scope}:{key}
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_STRATEGY: str = "sliding_window"  # "sliding_window" | "token_bucket"
    # تعريفات الـ scopes: (max_requests, window_seconds)
    RATE_LIMIT_SCOPES: dict = {
        "global":               (300,  60),   # 300 req/min لكل IP
        "ai_api":               (120,  60),   # transcribe + stream + speak per voice turn
        "auth_login":           (30,   300),  # 30 login/OTP steps per 5 min (2FA needs multiple POSTs)
        "auth_login_fail":      (10,   900),  # 10 فشل / 15 دقيقة ثم lockout
        "worker_api":           (120,  60),   # 120 req/min للعمال
        "worker_api_auth_fail": (5,    300),
        "admin_api":            (200,  60),
        "gate_api":             (600,  60),   # البوابات تُولّد طلبات أكثر
        "public_api":           (30,   60),
    }
    # مدة حظر IP بعد تجاوز الحد (بالثواني)
    RATE_LIMIT_BAN_DURATION_SECONDS: int = 900  # 15 دقيقة

    # ── Security ──────────────────────────────────────────────────────────────
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    PERMANENT_SESSION_LIFETIME_SECONDS: int = 8 * 3600  # 8 ساعات
    WTF_CSRF_ENABLED: bool = True
    ENFORCE_HTTPS: bool = _env_flag_enabled("BAUPASS_ENFORCE_HTTPS", "1")

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list = []  # override in subclasses

    # ── Background Tasks (RQ) ─────────────────────────────────────────────────
    RQ_DEFAULT_TIMEOUT: int = 300      # 5 دقائق
    RQ_QUEUES: list = ["critical", "high", "default", "low"]
    RQ_RETRY_MAX: int = 3
    RQ_RETRY_DELAYS: list = [60, 300, 900]  # ثانية: 1د / 5د / 15د

    # ── Observability ─────────────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    STRUCTURED_LOGS: bool = _env_flag_enabled("BAUPASS_STRUCTURED_LOGS", "1")

    # ── Object Storage ────────────────────────────────────────────────────────
    UPLOAD_BACKEND: str = os.getenv("UPLOAD_BACKEND", "local")  # "local" | "s3"
    S3_BUCKET: str = os.getenv("S3_BUCKET", "")
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "")  # MinIO support
    S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY", "")
    S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY", "")
    LOCAL_UPLOAD_DIR: Path = BASE_DIR / "backend" / "uploads"

    # ── Tenant Isolation ─────────────────────────────────────────────────────
    TENANT_ISOLATION_STRICT: bool = True  # يرفع خطأ إذا استُدعي repository بدون tenant
    TENANT_AUDIT_ALL_QUERIES: bool = False  # للتشخيص فقط


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SECRET_KEY = os.getenv("BAUPASS_SECRET_KEY", "dev-only-insecure-key-change-in-prod")
    SESSION_COOKIE_SECURE = False

    SQLITE_PATH = str(BASE_DIR / "backend" / "baupass.db")

    CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:5000", "http://localhost:5000"]

    RATE_LIMIT_ENABLED = False  # أسرع تطوير بدون rate limiting

    STRUCTURED_LOGS = False
    LOG_LEVEL = "DEBUG"

    TENANT_ISOLATION_STRICT = True  # اختبار العزل حتى في التطوير


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    SECRET_KEY = "testing-secret-key-not-for-production"
    SESSION_COOKIE_SECURE = False

    # قاعدة بيانات مؤقتة في الذاكرة للاختبارات
    DATABASE_URL = ""
    SQLITE_PATH = ":memory:"

    RATE_LIMIT_ENABLED = False
    WTF_CSRF_ENABLED = False

    # Redis وهمي للاختبارات
    REDIS_URL = "redis://localhost:6379/15"  # DB 15 للاختبارات

    TENANT_ISOLATION_STRICT = True


class ProductionConfig(BaseConfig):
    DEBUG = False

    # Persist SQLite to the Railway /data volume when no PostgreSQL is configured.
    # The get_db_path() function in database.py also auto-detects /data, but
    # setting SQLITE_PATH here makes the path explicit and avoids any ambiguity.
    SQLITE_PATH: str = os.getenv(
        "BAUPASS_DB_PATH",
        "/data/baupass.db" if os.path.isdir("/data") else "",
    ).strip()

    @classmethod
    def _resolve_public_base_url(cls) -> str:
        return (
            os.getenv("PUBLIC_BASE_URL", "")
            or os.getenv("RENDER_EXTERNAL_URL", "")
            or os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
        ).strip()

    @classmethod
    def validate(cls) -> None:
        """تحقق من أن جميع المتغيرات الضرورية موجودة قبل بدء التشغيل."""
        errors = []

        if not os.getenv("BAUPASS_SECRET_KEY", "").strip():
            errors.append("BAUPASS_SECRET_KEY is not set")
        elif len(os.getenv("BAUPASS_SECRET_KEY", "").strip()) < 32:
            errors.append("BAUPASS_SECRET_KEY must be at least 32 characters")

        database_url = os.getenv("DATABASE_URL", "").strip()
        allow_sqlite_prod = _env_flag_enabled("BAUPASS_ALLOW_SQLITE_PRODUCTION", "0")
        if not database_url and not allow_sqlite_prod:
            errors.append(
                "DATABASE_URL (PostgreSQL) is required in production. "
                "Set BAUPASS_ALLOW_SQLITE_PRODUCTION=1 only for temporary emergency fallback."
            )
        if database_url and not database_url.startswith("postgres"):
            errors.append("DATABASE_URL must point to PostgreSQL (postgres:// or postgresql://)")

        audit_key = os.getenv("BAUPASS_AUDIT_SIGNING_KEY", "").strip()
        if len(audit_key) < 32:
            errors.append("BAUPASS_AUDIT_SIGNING_KEY must be at least 32 characters")

        public_base_url = cls._resolve_public_base_url()
        if not public_base_url:
            errors.append(
                "PUBLIC_BASE_URL, RENDER_EXTERNAL_URL or RAILWAY_PUBLIC_DOMAIN must be set in production "
                "so external links and worker app URLs resolve correctly."
            )
        else:
            parsed = urlsplit(public_base_url)
            if not parsed.scheme or not parsed.hostname:
                errors.append("PUBLIC_BASE_URL must be a valid URL with scheme and hostname")
            elif parsed.scheme not in {"http", "https"}:
                errors.append("PUBLIC_BASE_URL must use https:// in production")
            elif parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                errors.append("PUBLIC_BASE_URL must use https:// in production for non-localhost domains")

        if not _env_flag_enabled("BAUPASS_ENFORCE_HTTPS", "1"):
            errors.append("BAUPASS_ENFORCE_HTTPS must remain enabled in production")

        if errors:
            msg = "\n".join(f"  - {e}" for e in errors)
            raise RuntimeError(
                f"[BauPass] Production configuration errors:\n{msg}\n\n"
                f"Run: python -c \"import secrets; print(secrets.token_hex(32))\"\n"
                f"to generate a secure SECRET_KEY."
            )

    # في الإنتاج تُقرأ المفاتيح من البيئة مع التحقق
    SECRET_KEY: str = os.getenv("BAUPASS_SECRET_KEY", "")


config_map: dict = {
    "development": DevelopmentConfig,
    "testing":     TestingConfig,
    "production":  ProductionConfig,
    "dev":         DevelopmentConfig,
    "test":        TestingConfig,
    "prod":        ProductionConfig,
}
