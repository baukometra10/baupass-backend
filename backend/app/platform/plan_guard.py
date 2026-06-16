"""Plan-based API guards for enterprise capabilities."""
from __future__ import annotations

from functools import wraps

from flask import g

from backend.app.platform.plan_entitlements import min_plan_for_capability, plan_includes


def company_has_capability(db, company_id: str | None, capability_id: str) -> bool:
    from backend.server import get_company_plan

    if not company_id:
        return False
    plan = get_company_plan(db, company_id)
    return plan_includes(plan, min_plan_for_capability(capability_id))


def capability_blocked_response(db, company_id: str | None, capability_id: str):
    from backend.server import feature_not_available_response, get_company_plan

    plan = get_company_plan(db, company_id) if company_id else "starter"
    return feature_not_available_response(capability_id, plan)


def require_plan_capability(capability_id: str):
    """Decorator: 403 if company plan does not include capability."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from backend.server import feature_not_available_response, get_company_plan, get_db

            db = get_db()
            company_id = g.current_user.get("company_id")
            if g.current_user.get("role") == "superadmin":
                return fn(*args, **kwargs)
            plan = get_company_plan(db, company_id)
            if not plan_includes(plan, min_plan_for_capability(capability_id)):
                return feature_not_available_response(capability_id, plan)
            return fn(*args, **kwargs)

        return wrapper

    return decorator
