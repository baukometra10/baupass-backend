"""
BauPass – Distributed Rate Limiting Middleware (Redis-based)
=============================================================
يحل المشكلة الأساسية في server.py الحالي:
  - الـ rate limiting الحالي مخزَّن في ذاكرة Python process واحد
  - مع multiple workers (Gunicorn/Waitress) كل process له ذاكرة مستقلة
  - النتيجة: يمكن تجاوز الحد بإرسال X طلبات لكل process

هذا الملف يستخدم Redis كـ shared state مع:
  1. Sliding Window algorithm (أدق من Fixed Window)
  2. Lua script atomic execution (يمنع race conditions)
  3. Fallback لـ in-memory إذا Redis غير متاح
  4. IP ban mechanism للهجمات المتكررة
  5. Whitelist للـ IPs الداخلية والـ health checks
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import threading
import time
from collections import defaultdict, deque
from functools import wraps
from typing import Optional, Tuple

from flask import Flask, Request, g, jsonify, request

logger = logging.getLogger("baupass.rate_limit")

# ── Lua Script للـ Sliding Window (atomic في Redis) ─────────────────────────
# يُنفَّذ كـ atomic operation لمنع race conditions
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local ban_key = KEYS[2]
local ban_duration = tonumber(ARGV[4])

-- هل هذا الـ IP محظور؟
if redis.call('EXISTS', ban_key) == 1 then
    local ttl = redis.call('TTL', ban_key)
    return {-1, ttl}
end

-- حذف الطلبات القديمة خارج النافذة
local cutoff = now - window * 1000
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)

-- عدد الطلبات الحالية
local current = redis.call('ZCARD', key)

if current >= limit then
    -- حظر IP إذا تجاوز الحد بشكل متكرر
    if ban_duration > 0 and current >= limit * 2 then
        redis.call('SET', ban_key, '1', 'EX', ban_duration)
    end
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if #oldest > 0 then
        retry_after = math.ceil((tonumber(oldest[2]) + window * 1000 - now) / 1000)
    end
    return {0, math.max(1, retry_after)}
end

-- تسجيل الطلب الحالي
local member = now .. ':' .. math.random(1000000)
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window + 1)

return {1, limit - current - 1}
"""


class RedisRateLimiter:
    """
    Rate limiter موزَّع يستخدم Redis مع Sliding Window algorithm.
    """

    def __init__(self, redis_client, config: dict):
        self._redis = redis_client
        self._scopes: dict = config.get("RATE_LIMIT_SCOPES", {})
        self._ban_duration: int = config.get("RATE_LIMIT_BAN_DURATION_SECONDS", 900)
        self._lua_sha: Optional[str] = None
        self._load_lua_script()

    def _load_lua_script(self) -> None:
        try:
            self._lua_sha = self._redis.script_load(_SLIDING_WINDOW_LUA)
        except Exception as exc:
            logger.warning("Could not load Lua script: %s. Using EVAL fallback.", exc)
            self._lua_sha = None

    def check(
        self,
        scope: str,
        identifier: str,  # IP address أو user_id
    ) -> Tuple[bool, int]:
        """
        يتحقق من الـ rate limit.

        Returns:
            (allowed, retry_after_seconds)
            allowed = True → الطلب مسموح
            allowed = False → الطلب محظور، retry_after = ثواني الانتظار
        """
        if scope not in self._scopes:
            return True, 0

        limit, window = self._scopes[scope]

        # بناء مفاتيح Redis
        key_hash = hashlib.sha256(f"{scope}:{identifier}".encode()).hexdigest()[:16]
        rate_key = f"rl:{scope}:{key_hash}"
        ban_key = f"rl:ban:{key_hash}"

        now_ms = int(time.time() * 1000)

        try:
            if self._lua_sha:
                result = self._redis.evalsha(
                    self._lua_sha,
                    2,
                    rate_key, ban_key,
                    now_ms, window, limit, self._ban_duration,
                )
            else:
                result = self._redis.eval(
                    _SLIDING_WINDOW_LUA,
                    2,
                    rate_key, ban_key,
                    now_ms, window, limit, self._ban_duration,
                )

            status, value = int(result[0]), int(result[1])

            if status == -1:  # IP محظور
                return False, value

            return status == 1, value

        except Exception as exc:
            logger.error("Redis rate limit check failed: %s", exc)
            # في حالة فشل Redis → نسمح بالطلب (fail open) لتجنب outage
            return True, 0

    def is_banned(self, identifier: str) -> Tuple[bool, int]:
        """يتحقق إذا كان IP محظوراً."""
        try:
            key_hash = hashlib.sha256(identifier.encode()).hexdigest()[:16]
            ban_key = f"rl:ban:{key_hash}"
            ttl = self._redis.ttl(ban_key)
            if ttl > 0:
                return True, ttl
            return False, 0
        except Exception:
            return False, 0

    def ban_ip(self, identifier: str, duration_seconds: int, reason: str = "") -> None:
        """حظر IP يدوي (من admin)."""
        try:
            key_hash = hashlib.sha256(identifier.encode()).hexdigest()[:16]
            ban_key = f"rl:ban:{key_hash}"
            self._redis.set(ban_key, reason or "manual_ban", ex=duration_seconds)
            logger.warning("IP banned: %s for %ds (reason: %s)", identifier, duration_seconds, reason)
        except Exception as exc:
            logger.error("Failed to ban IP: %s", exc)

    def reset(self, scope: str, identifier: str) -> None:
        """إعادة تعيين عداد IP (من admin)."""
        try:
            key_hash = hashlib.sha256(f"{scope}:{identifier}".encode()).hexdigest()[:16]
            rate_key = f"rl:{scope}:{key_hash}"
            self._redis.delete(rate_key)
        except Exception as exc:
            logger.error("Failed to reset rate limit: %s", exc)


class InMemoryRateLimiter:
    """
    Rate limiter احتياطي يعمل في الذاكرة عند غياب Redis.
    تحذير: لا يعمل مع multiple processes. للتطوير فقط.
    """

    def __init__(self, config: dict):
        self._scopes: dict = config.get("RATE_LIMIT_SCOPES", {})
        self._windows: dict = defaultdict(deque)
        self._bans: dict = {}
        self._lock = threading.Lock()

    def check(self, scope: str, identifier: str) -> Tuple[bool, int]:
        if scope not in self._scopes:
            return True, 0

        limit, window = self._scopes[scope]
        now = time.monotonic()
        key = f"{scope}:{identifier}"

        with self._lock:
            # هل محظور؟
            if key in self._bans and self._bans[key] > now:
                return False, int(self._bans[key] - now)

            # حذف الطلبات القديمة
            q = self._windows[key]
            cutoff = now - window
            while q and q[0] <= cutoff:
                q.popleft()

            if len(q) >= limit:
                retry_after = max(1, int(q[0] + window - now)) if q else window
                return False, retry_after

            q.append(now)
            return True, limit - len(q)

    def is_banned(self, identifier: str) -> Tuple[bool, int]:
        now = time.monotonic()
        for key, exp in self._bans.items():
            if identifier in key and exp > now:
                return True, int(exp - now)
        return False, 0

    def ban_ip(self, identifier: str, duration_seconds: int, reason: str = "") -> None:
        with self._lock:
            self._bans[f"ban:{identifier}"] = time.monotonic() + duration_seconds

    def reset(self, scope: str, identifier: str) -> None:
        with self._lock:
            self._windows.pop(f"{scope}:{identifier}", None)


# ── IPs الداخلية التي لا تخضع لـ rate limiting ──────────────────────────────
_INTERNAL_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
]

_EXCLUDED_PATHS = frozenset({
    "/api/health",
    "/api/public/branding",
    "/api/public/tenant-branding",
    "/api/session/bootstrap",
    "/favicon.ico",
})


def _get_client_ip(req: Request) -> str:
    forwarded = (req.headers.get("X-Forwarded-For") or "").strip()
    ip = forwarded.split(",", 1)[0].strip() if forwarded else (req.remote_addr or "unknown")
    return ip


def _is_internal_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _INTERNAL_NETWORKS)
    except ValueError:
        return False


def register_rate_limit_middleware(app: Flask) -> None:
    """
    يُسجّل rate limiting middleware على Flask app.
    يُستدعى من app factory.
    """
    @app.before_request
    def _rate_limit_check():
        if not app.config.get("RATE_LIMIT_ENABLED", True):
            return None

        path = request.path
        if (
            path in _EXCLUDED_PATHS
            or path.startswith("/api/health")
            or path.startswith("/api/ai/")
            or path.startswith("/metrics")
            or path.startswith("/static/")
        ):
            return None

        client_ip = _get_client_ip(request)

        if _is_internal_ip(client_ip):
            return None

        limiter = app.extensions.get("rate_limiter")
        if not limiter:
            return None

        # تحديد الـ scope بناءً على المسار
        scope = _detect_scope(path, request.method)

        allowed, retry_after = limiter.check(scope, client_ip)

        if not allowed:
            logger.warning(
                "Rate limit exceeded: scope=%s ip=%s path=%s retry_after=%ds",
                scope, client_ip, path, retry_after,
            )
            response = jsonify({
                "error": "rate_limited",
                "message": "Too many requests. Please try again later.",
                "retryAfterSeconds": retry_after,
            })
            response.headers["Retry-After"] = str(retry_after)
            response.headers["X-RateLimit-Scope"] = scope
            return response, 429

        return None


def _detect_scope(path: str, method: str) -> str:
    """يُحدد الـ scope المناسب للـ rate limit بناءً على المسار."""
    if path.startswith("/api/ai/"):
        return "ai_api"
    if path in {"/api/login", "/api/logout"} and method in {"POST", "PUT"}:
        return "auth_login"
    if "/api/auth/login" in path or "/api/worker-app/auth" in path:
        return "auth_login"
    if "/api/gate/" in path or "/api/scan" in path:
        return "gate_api"
    if "/api/worker-app/" in path:
        return "worker_api"
    if "/api/admin/" in path or "/api/companies" in path:
        return "admin_api"
    if "/api/public/" in path:
        return "public_api"
    return "global"


def build_rate_limiter(app: Flask):
    """
    يبني وينشئ rate limiter المناسب (Redis أو in-memory).
    يُستدعى من init_extensions.
    """
    redis_client = app.extensions.get("redis")

    if redis_client:
        limiter = RedisRateLimiter(redis_client, app.config)
        logger.info("Rate limiter: Redis (distributed)")
    else:
        limiter = InMemoryRateLimiter(app.config)
        logger.warning(
            "Rate limiter: in-memory (NOT suitable for multiple workers). "
            "Connect Redis for distributed rate limiting."
        )

    app.extensions["rate_limiter"] = limiter
    return limiter
