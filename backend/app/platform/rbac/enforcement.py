"""Enterprise RBAC enforcement (Phase B) — layered on legacy roles."""
from __future__ import annotations

import json
import secrets
from typing import Any

# permission -> allowed HTTP methods for write-capable roles
ENTERPRISE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "auditor": frozenset(
        {
            "audit.read",
            "reports.read",
            "reports.export",
            "workers.read",
            "access.read",
        }
    ),
    "compliance_officer": frozenset(
        {
            "audit.read",
            "reports.read",
            "reports.export",
            "reports.send",
            "workers.read",
            "documents.read",
            "governance.retention",
            "governance.legal_hold",
        }
    ),
    "security_officer": frozenset(
        {
            "audit.read",
            "reports.read",
            "security.read",
            "security.export",
            "workers.read",
            "access.read",
        }
    ),
    "department_admin": frozenset({"workers.read", "workers.write", "reports.read", "access.read"}),
    "department_manager": frozenset({"workers.read", "workers.write", "reports.read", "access.read"}),
    "site_manager": frozenset({"workers.read", "workers.write", "access.read", "access.write", "reports.read"}),
    "regional_manager": frozenset({"workers.read", "reports.read", "reports.export", "access.read"}),
}

READ_ONLY_ENTERPRISE_ROLES = frozenset({"auditor"})


def _table_exists(db, name: str) -> bool:
    try:
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (name,),
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def load_user_enterprise_roles(db, user: dict[str, Any]) -> list[str]:
    if not user or not _table_exists(db, "enterprise_role_assignments"):
        return []
    user_id = str(user.get("id") or "")
    company_id = str(user.get("company_id") or "")
    if not user_id:
        return []
    rows = db.execute(
        """
        SELECT DISTINCT role_id FROM enterprise_role_assignments
        WHERE user_id = ?
          AND (company_id IS NULL OR company_id = '' OR company_id = ? OR ? = '')
        """,
        (user_id, company_id, company_id),
    ).fetchall()
    return [str(r["role_id"]) for r in rows if r and r["role_id"]]


def user_permissions(db, user: dict[str, Any]) -> set[str]:
    perms: set[str] = set()
    legacy = str(user.get("role") or "")
    if legacy == "superadmin":
        perms.add("*")
        return perms
    if legacy == "company-admin":
        perms.update(
            {
                "workers.read",
                "workers.write",
                "access.read",
                "access.write",
                "reports.read",
                "reports.export",
                "reports.send",
                "audit.read",
                "governance.retention",
                "governance.legal_hold",
            }
        )
    for role_id in load_user_enterprise_roles(db, user):
        perms.update(ENTERPRISE_ROLE_PERMISSIONS.get(role_id, frozenset()))
    return perms


def has_permission(db, user: dict[str, Any], permission: str) -> bool:
    perms = user_permissions(db, user)
    if "*" in perms:
        return True
    return permission in perms


def is_auditor_read_only(db, user: dict[str, Any]) -> bool:
    if str(user.get("role") or "") == "superadmin":
        return False
    roles = set(load_user_enterprise_roles(db, user))
    if not roles:
        return False
    if roles <= READ_ONLY_ENTERPRISE_ROLES:
        return True
    return False


def apply_entra_group_roles(db, user_id: str, company_id: str | None, group_ids: list[str]) -> list[str]:
    """Map Entra group object IDs to enterprise roles for this user."""
    if not _table_exists(db, "entra_group_role_mappings") or not group_ids:
        return []
    assigned: list[str] = []
    for gid in group_ids:
        gid = str(gid or "").strip()
        if not gid:
            continue
        rows = db.execute(
            """
            SELECT enterprise_role_id FROM entra_group_role_mappings
            WHERE entra_group_id = ?
              AND (company_id IS NULL OR company_id = '' OR company_id = ?)
            """,
            (gid, str(company_id or "")),
        ).fetchall()
        for row in rows:
            role_id = str(row["enterprise_role_id"])
            if not role_id:
                continue
            existing = db.execute(
                """
                SELECT id FROM enterprise_role_assignments
                WHERE user_id = ? AND role_id = ? AND COALESCE(company_id, '') = ?
                LIMIT 1
                """,
                (user_id, role_id, str(company_id or "")),
            ).fetchone()
            if existing:
                assigned.append(role_id)
                continue
            from backend.server import now_iso

            db.execute(
                """
                INSERT INTO enterprise_role_assignments
                (id, user_id, company_id, role_id, scope_type, scope_id, source, created_at)
                VALUES (?, ?, ?, ?, 'company', ?, 'entra_group', ?)
                """,
                (
                    f"era-{secrets.token_hex(8)}",
                    user_id,
                    str(company_id or "") or None,
                    role_id,
                    str(company_id or "") or None,
                    now_iso(),
                ),
            )
            assigned.append(role_id)
    if assigned:
        db.commit()
    return assigned


def parse_entra_group_mapping_env() -> list[dict[str, str]]:
    import os

    raw = (os.getenv("BAUPASS_ENTRA_GROUP_ROLE_MAP") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
