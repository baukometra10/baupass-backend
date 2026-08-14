"""Office operator RBAC helpers.

company-admin  = owner: full access including payroll/contracts/accounting
office         = day-to-day ops without sensitive finance/legal surfaces
turnstile      = gate only
"""
from __future__ import annotations

from flask import request

OWNER_ROLES = frozenset({"superadmin", "company-admin"})
OPS_STAFF_ROLES = frozenset({"superadmin", "company-admin", "office"})
COMPANY_SCOPED_ROLES = frozenset({"company-admin", "office", "turnstile"})

# Paths that must stay owner-only even when require_roles includes company-admin.
_OWNER_ONLY_PATH_MARKERS = (
    "/api/payroll",
    "/api/accounting",
    "/api/contracts",
    "/api/invoices",
    "/api/billing",
    "/api/audit",
    "/admin-security",
    "/set-admin-password",
    "/export/audit-logs",
    "/api/platform/accounting",
    "/api/platform/lohn",
    "/workpass-lohn",
    "/sso-enter",
)


def normalize_role(user: dict | None) -> str:
    return str((user or {}).get("role") or "").strip().lower()


def is_office_role(user: dict | None) -> bool:
    return normalize_role(user) == "office"


def is_owner_role(user: dict | None) -> bool:
    return normalize_role(user) in OWNER_ROLES


def path_is_owner_only(path: str | None = None) -> bool:
    raw = str(path if path is not None else getattr(request, "path", "") or "").lower()
    if "/api/public/" in raw:
        return False
    return any(marker in raw for marker in _OWNER_ONLY_PATH_MARKERS)


def office_may_use_company_admin_route(path: str | None = None) -> bool:
    """Whether an office user may pass a require_roles(..., company-admin, ...) gate."""
    return not path_is_owner_only(path)
