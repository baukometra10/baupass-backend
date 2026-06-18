"""
BauPass – Flask Extensions
===========================
تهيئة جميع Flask extensions في مكان واحد.
يُستدعى init_extensions() من app factory بعد إنشاء Flask app.
"""
from __future__ import annotations

import logging
import os
import socket
from typing import Optional, TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger("baupass.extensions")

# ── Redis Client (محوري لـ: rate limiting, sessions, RQ, cache) ─────────────
redis_client = None  # يُهيأ في init_extensions


def init_extensions(app: "Flask") -> None:
    """يُهيئ جميع extensions ويربطها بـ Flask app."""
    _init_redis(app)


def _init_redis(app: "Flask") -> None:
    """
    تهيئة Redis مع connection pool.
    إذا Redis غير متاح: يُسجّل تحذيراً ويعمل بدونه (degraded mode).
    """
    global redis_client

    redis_url = str(app.config.get("REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
    if not redis_url:
        logger.info(
            "Redis not configured (REDIS_URL unset). "
            "Rate limits use in-memory; background jobs run synchronously."
        )
        redis_client = None
        return

    try:
        parsed = urlparse(redis_url)
        host = parsed.hostname or "localhost"
        port = int(parsed.port or 6379)
        try:
            with socket.create_connection((host, port), timeout=0.75):
                pass
        except OSError as exc:
            raise ConnectionError(f"{host}:{port}") from exc

        import redis

        pool = redis.ConnectionPool.from_url(
            redis_url,
            max_connections=app.config.get("REDIS_MAX_CONNECTIONS", 20),
            socket_timeout=app.config.get("REDIS_SOCKET_TIMEOUT", 3.0),
            socket_connect_timeout=3.0,
            retry_on_timeout=app.config.get("REDIS_RETRY_ON_TIMEOUT", True),
            decode_responses=True,
        )
        redis_client = redis.Redis(connection_pool=pool)

        # اختبار الاتصال
        redis_client.ping()
        app.extensions["redis"] = redis_client
        logger.info("Redis connected: %s", redis_url.split("@")[-1])

    except ImportError:
        logger.warning(
            "redis package not installed. Rate limiting will fall back to in-memory. "
            "Install: pip install redis"
        )
        redis_client = None

    except Exception as exc:
        logger.warning(
            "Redis unavailable (%s). Rate limiting falls back to in-memory. "
            "Set REDIS_URL or start Redis.",
            exc,
        )
        redis_client = None


def get_redis():
    """
    يُعيد Redis client الحالي.
    يُستدعى من داخل request context أو background tasks.
    """
    return redis_client
