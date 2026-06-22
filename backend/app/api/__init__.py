"""
WorkPass – API Blueprints Registry
===================================
كل blueprint يمثل domain منفصل.
يُضاف blueprint جديد هنا عند نقله من server.py.

الانتقال التدريجي:
  server.py الحالي يستمر في العمل.
  يُنقل route تلو route إلى هنا تدريجياً.
  عند اكتمال النقل، يُحذف server.py.
"""
from flask import Blueprint

# ── Blueprint Definitions ────────────────────────────────────────────────────
auth_bp        = Blueprint("auth",        __name__)
workers_bp     = Blueprint("workers",     __name__)
companies_bp   = Blueprint("companies",   __name__)
attendance_bp  = Blueprint("attendance",  __name__)
admin_bp       = Blueprint("admin",       __name__)
public_bp      = Blueprint("public",      __name__)
health_bp      = Blueprint("health",      __name__)
worker_app_bp  = Blueprint("worker_app",  __name__)

# ── Route Registrations ───────────────────────────────────────────────────────
# يُستورد هنا لتفعيل تسجيل الـ routes
from . import (  # noqa: F401, E402
    auth,
    health_routes,
)

# Future migration: add additional route modules here as handlers are moved from server.py.
# Existing legacy bridge modules live under backend/app/api/worker_app_routes.py and backend/app/api/shift_routes.py.

__all__ = [
    "auth_bp",
    "workers_bp",
    "companies_bp",
    "attendance_bp",
    "admin_bp",
    "public_bp",
    "health_bp",
    "worker_app_bp",
]
