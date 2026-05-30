"""Enterprise RBAC enforcement helpers."""
from __future__ import annotations

import sqlite3
import unittest

READ_ONLY_ENTERPRISE_ROLES = frozenset({"auditor"})


def load_user_enterprise_roles(conn, user):
    user_id = str(user.get("id") or "")
    company_id = str(user.get("company_id") or "")
    rows = conn.execute(
        """
        SELECT DISTINCT role_id FROM enterprise_role_assignments
        WHERE user_id = ? AND (company_id IS NULL OR company_id = '' OR company_id = ?)
        """,
        (user_id, company_id),
    ).fetchall()
    return [str(r[0]) for r in rows]


def is_auditor_read_only(conn, user):
    if str(user.get("role") or "") == "superadmin":
        return False
    roles = set(load_user_enterprise_roles(conn, user))
    return bool(roles) and roles <= READ_ONLY_ENTERPRISE_ROLES


def user_permissions(conn, user):
    if str(user.get("role") or "") == "superadmin":
        return {"*"}
    perms = set()
    if str(user.get("role") or "") == "company-admin":
        perms.update({"reports.export", "audit.read", "governance.retention"})
    if "auditor" in load_user_enterprise_roles(conn, user):
        perms.update({"audit.read", "reports.export"})
    return perms


class RbacEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE enterprise_role_assignments (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                company_id TEXT,
                role_id TEXT NOT NULL,
                scope_type TEXT DEFAULT 'company',
                scope_id TEXT,
                source TEXT DEFAULT 'manual',
                created_at TEXT NOT NULL
            );
            """
        )

    def test_auditor_read_only(self):
        self.conn.execute(
            "INSERT INTO enterprise_role_assignments VALUES ('1','u1','c1','auditor','company','c1','manual','now')"
        )
        self.conn.commit()
        user = {"id": "u1", "role": "company-admin", "company_id": "c1"}
        self.assertTrue(is_auditor_read_only(self.conn, user))
        perms = user_permissions(self.conn, user)
        self.assertIn("audit.read", perms)

    def test_company_admin_has_export(self):
        user = {"id": "u2", "role": "company-admin", "company_id": "c1"}
        perms = user_permissions(self.conn, user)
        self.assertIn("reports.export", perms)


if __name__ == "__main__":
    unittest.main()
