"""
WorkPass – Flask Application Factory
====================================
الغرض: إنشاء تطبيق Flask بطريقة factory تدعم بيئات متعددة (dev/test/prod)
       وتفصل التهيئة عن تعريف التطبيق.

الاستخدام:
    من server.py الحالي:
        from app import create_app
        app = create_app()

    للاختبار:
        app = create_app(config_name="testing")

الانتقال التدريجي: هذا الملف يعمل بجانب server.py ولا يحذفه.
                  كل module يُنقل هنا يُحذف من server.py تدريجياً.
"""
from __future__ import annotations

import logging
import os
import atexit
from typing import Optional

from flask import Flask

from .config import config_map, ProductionConfig
from .extensions import redis_client, init_extensions
from .database import close_postgres_pool, init_postgres_pool, is_postgres_configured
from .platform_guard import enforce_platform_guards
from .tasks import init_task_queues
from .middleware.security import register_security_middleware
from .middleware.rate_limiting import register_rate_limit_middleware
from .middleware.tenant import TenantMiddleware
from .middleware.logging_mw import register_logging_middleware


logger = logging.getLogger("baupass.factory")


def create_app(config_name: Optional[str] = None) -> Flask:
    """
    Flask Application Factory.

    Args:
        config_name: 'development' | 'testing' | 'production'
                     If None, reads BAUPASS_ENV env var (defaults to 'production').
    """
    if config_name is None:
        config_name = os.getenv("BAUPASS_ENV", "production").lower()

    cfg_class = config_map.get(config_name, ProductionConfig)

    app = Flask(__name__)
    app.config.from_object(cfg_class)

    if config_name in {"production", "prod"}:
        ProductionConfig.validate()
        enforce_platform_guards(app.config)

    # ── Extensions (Redis, etc.) ──────────────────────────────────────────────
    init_extensions(app)
    init_task_queues(str(app.config.get("REDIS_URL") or os.getenv("REDIS_URL") or "").strip())

    # ── Database runtime adapters (PostgreSQL transition path) ──────────────
    if is_postgres_configured(app.config):
        ok = init_postgres_pool(app.config)
        if not ok and config_name in {"production", "prod"}:
            raise RuntimeError("PostgreSQL pool initialization failed in production")
        atexit.register(close_postgres_pool)

    # ── Middleware ────────────────────────────────────────────────────────────
    register_logging_middleware(app)
    register_security_middleware(app)
    register_rate_limit_middleware(app)

    # ── Blueprints (routes) ───────────────────────────────────────────────────
    _register_blueprints(app)

    # ── Startup hooks ─────────────────────────────────────────────────────────
    _register_startup_hooks(app)

    return app


def _register_blueprints(app: Flask) -> None:
    """تسجيل جميع blueprints. يُضاف blueprint جديد هنا عند نقله من server.py."""
    from .api import (
        auth_bp,
        workers_bp,
        companies_bp,
        attendance_bp,
        admin_bp,
        public_bp,
        health_bp,
    )

    prefix = "/api"
    app.register_blueprint(auth_bp,        url_prefix=prefix)
    app.register_blueprint(workers_bp,     url_prefix=prefix)
    app.register_blueprint(companies_bp,   url_prefix=prefix)
    app.register_blueprint(attendance_bp,  url_prefix=prefix)
    app.register_blueprint(admin_bp,       url_prefix=prefix)
    app.register_blueprint(public_bp,      url_prefix=f"{prefix}/public")
    app.register_blueprint(health_bp,      url_prefix=prefix)


def _register_startup_hooks(app: Flask) -> None:
    @app.before_request
    def _attach_request_id():
        """يُرفق X-Request-Id لكل طلب لتتبعه في اللوقات."""
        import uuid
        from flask import g, request
        g.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())

    @app.teardown_appcontext
    def _close_db(exc: Optional[Exception]) -> None:
        """يُغلق اتصال قاعدة البيانات في نهاية كل طلب."""
        from flask import g
        db = g.pop("_db", None)
        if db is not None:
            db.close()

