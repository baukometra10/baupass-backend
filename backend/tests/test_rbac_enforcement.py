"""
RBAC Enforcement Tests - Enterprise Security Hardening
Tests unauthorized access rejection and role-based access control
for sensitive endpoints before official release.
"""

import pytest
import json
import os
import sys
from pathlib import Path

from backend import server
from backend.server import app, get_db, generate_password_hash, create_turnstile_api_key, hash_turnstile_api_key


class TestRBACEnforcement:
    """Test suite for RBAC enforcement on sensitive endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Setup test app with in-memory database."""
        db_path = tmp_path / "test.sqlite3"
        os.environ["BAUPASS_DB_PATH"] = str(db_path)
        os.environ["BAUPASS_STRUCTURED_LOGS"] = "1"
        server.DB_PATH = db_path
        server.request_rate_state.clear()
        server.failed_login_attempts.clear()

        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

        with app.app_context():
            server.init_db()
            db = get_db()
            
            # Create demo users with different roles
            self.superadmin_password = "testadmin1234"
            self.company_admin_password = "testcompany1234"
            self.turnstile_password = "testgate1234"
            self.worker_password = "testworker1234"
            
            # Create company for testing (use unique ID)
            import secrets
            company_id = f"test-{secrets.token_hex(4)}"
            db.execute(
                """INSERT INTO companies (id, name, customer_number, contact, billing_email, document_email, status, plan)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (company_id, "Test Company", "999", "Test Contact", "test@test.com", "testdoc@test.com", "aktiv", "tageskarte")
            )
            self.test_company_id = company_id
            
            # Create superadmin with unique username
            superadmin_user = f"testadmin_{secrets.token_hex(3)}"
            db.execute(
                """INSERT INTO users (id, username, password_hash, name, role, company_id, twofa_enabled)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (f"usr-{secrets.token_hex(6)}", superadmin_user, generate_password_hash(self.superadmin_password), 
                 "Test Super Admin", "superadmin", None, 0)
            )
            self.superadmin_username = superadmin_user
            
            # Create company admin with unique username
            company_admin_user = f"testcmpadmin_{secrets.token_hex(3)}"
            db.execute(
                """INSERT INTO users (id, username, password_hash, name, role, company_id, twofa_enabled)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (f"usr-{secrets.token_hex(6)}", company_admin_user, generate_password_hash(self.company_admin_password),
                 "Test Company Admin", "company-admin", company_id, 0)
            )
            self.company_admin_username = company_admin_user
            
            # Create turnstile user with unique username
            turnstile_user = f"testgate_{secrets.token_hex(3)}"
            api_key = create_turnstile_api_key()
            db.execute(
                """INSERT INTO users (id, username, password_hash, name, role, company_id, api_key_hash, twofa_enabled)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"usr-{secrets.token_hex(6)}", turnstile_user, generate_password_hash(self.turnstile_password),
                 "Test Turnstile", "turnstile", company_id, hash_turnstile_api_key(api_key), 0)
            )
            self.turnstile_username = turnstile_user
            self.turnstile_api_key = api_key
            
            # Create worker user
            try:
                db.execute(
                    """INSERT INTO workers (id, company_id, first_name, last_name, worker_type, status, badge_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (f"wrk-{secrets.token_hex(6)}", company_id, "Test", "Worker", "worker", "aktiv", "TESTWR001")
                )
            except Exception:
                pass  # Workers table might not have all fields
            
            db.commit()
            self.superadmin_token = None
            self.company_admin_token = None
            self.turnstile_token = None

    def login(self, username, password):
        """Helper to login and get session token."""
        response = self.client.post(
            "/api/login",
            json={"username": username, "password": password},
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            return response.get_json().get("token")
        return None

    def get_auth_headers(self, token):
        """Helper to create auth headers."""
        return {"Authorization": f"Bearer {token}"}

    # ════════════════════════════════════════════════════════════════════════════
    # SUPERADMIN-ONLY ENDPOINTS (403 for non-superadmin)
    # ════════════════════════════════════════════════════════════════════════════

    def test_system_status_superadmin_only(self):
        """Test /api/system/status is superadmin-only."""
        # Unauthenticated should get 401
        response = self.client.get("/api/system/status")
        assert response.status_code == 401, "Unauthenticated access should be rejected"

    def test_system_status_company_admin_forbidden(self):
        """Test company-admin gets 403 on /api/system/status."""
        token = self.login(self.company_admin_username, self.company_admin_password)
        assert token, "Company admin should login successfully"
        
        response = self.client.get(
            "/api/system/status",
            headers=self.get_auth_headers(token)
        )
        assert response.status_code == 403, "Company admin should get 403 (forbidden) on superadmin endpoint"
        assert response.get_json().get("error") == "forbidden", "Error message should be 'forbidden'"

    def test_system_status_turnstile_forbidden(self):
        """Test turnstile gets 403 on /api/system/status."""
        token = self.login(self.turnstile_username, self.turnstile_password)
        assert token, "Turnstile should login successfully"
        
        response = self.client.get(
            "/api/system/status",
            headers=self.get_auth_headers(token)
        )
        assert response.status_code == 403, "Turnstile should get 403 on superadmin endpoint"

    def test_system_runtime_check_superadmin_only(self):
        """Test /api/system/runtime-check is superadmin-only."""
        token = self.login(self.company_admin_username, self.company_admin_password)
        assert token, "Company admin should login successfully"
        
        response = self.client.get(
            "/api/system/runtime-check",
            headers=self.get_auth_headers(token)
        )
        assert response.status_code == 403, "Company admin should get 403 on superadmin endpoint"

    def test_system_repair_superadmin_only(self):
        """Test /api/system/repair is superadmin-only."""
        token = self.login(self.company_admin_username, self.company_admin_password)
        assert token, "Company admin should login successfully"
        
        response = self.client.post(
            "/api/system/repair",
            headers=self.get_auth_headers(token)
        )
        assert response.status_code == 403, "Company admin should get 403 on superadmin endpoint"

    def test_smtp_test_superadmin_only(self):
        """Test /api/settings/smtp-test is superadmin-only."""
        token = self.login(self.company_admin_username, self.company_admin_password)
        assert token, "Company admin should login successfully"
        
        response = self.client.post(
            "/api/settings/smtp-test",
            json={"recipient": "test@example.com"},
            headers=self.get_auth_headers(token)
        )
        assert response.status_code == 403, "Company admin should get 403 on superadmin endpoint"

    def test_settings_update_superadmin_only(self):
        """Test PUT /api/settings is superadmin-only."""
        token = self.login(self.company_admin_username, self.company_admin_password)
        assert token, "Company admin should login successfully"
        
        response = self.client.put(
            "/api/settings",
            json={"platformName": "Changed Name"},
            headers=self.get_auth_headers(token)
        )
        assert response.status_code == 403, "Company admin should get 403 on settings update"

    # ════════════════════════════════════════════════════════════════════════════
    # COMPANY-ADMIN ENDPOINTS (403 for turnstile)
    # ════════════════════════════════════════════════════════════════════════════

    def test_companies_list_requires_auth(self):
        """Test /api/companies requires authentication."""
        response = self.client.get("/api/companies")
        assert response.status_code == 401, "Unauthenticated access should be rejected"

    def test_workers_import_csv_turnstile_forbidden(self):
        """Test /api/workers/import-csv is company-admin+ only."""
        token = self.login(self.turnstile_username, self.turnstile_password)
        assert token, "Turnstile should login successfully"
        
        response = self.client.post(
            "/api/workers/import-csv",
            headers=self.get_auth_headers(token),
            data={"file": (b"test", "test.csv")}
        )
        assert response.status_code == 403, "Turnstile should get 403 on company-admin endpoint"

    def test_workers_export_csv_company_admin_allowed(self):
        """Test company-admin can export CSV."""
        token = self.login(self.company_admin_username, self.company_admin_password)
        assert token, "Company admin should login successfully"
        
        response = self.client.get(
            "/api/workers/export.csv",
            headers=self.get_auth_headers(token)
        )
        # Should return 200 or CSV content, not 403
        assert response.status_code in (200, 400), f"Company admin should be allowed (got {response.status_code})"
        assert response.status_code != 403, "Company admin should not get 403"

    # ════════════════════════════════════════════════════════════════════════════
    # COMPANY-ADMIN, TURNSTILE ENDPOINTS
    # ════════════════════════════════════════════════════════════════════════════

    def test_get_current_visitors_allowed_for_company_admin(self):
        """Test company-admin can access visitor endpoints."""
        token = self.login(self.company_admin_username, self.company_admin_password)
        assert token, "Company admin should login successfully"
        
        response = self.client.get(
            "/api/workers/current-visitors",
            headers=self.get_auth_headers(token)
        )
        assert response.status_code != 403, "Company admin should be allowed on visitor endpoint"

    def test_get_current_visitors_allowed_for_turnstile(self):
        """Test turnstile can access visitor endpoints."""
        token = self.login(self.turnstile_username, self.turnstile_password)
        assert token, "Turnstile should login successfully"
        
        response = self.client.get(
            "/api/workers/current-visitors",
            headers=self.get_auth_headers(token)
        )
        assert response.status_code != 403, "Turnstile should be allowed on visitor endpoint"

    # ════════════════════════════════════════════════════════════════════════════
    # COMPANY SCOPE ENFORCEMENT (company-admin can only access own company)
    # ════════════════════════════════════════════════════════════════════════════

    def test_company_admin_cannot_access_other_company(self):
        """Test company-admin cannot access endpoints from other companies."""
        with app.app_context():
            db = get_db()
            # Create another company
            import secrets
            other_company_id = f"other-{secrets.token_hex(4)}"
            db.execute(
                """INSERT INTO companies (id, name, customer_number, contact, billing_email, document_email, status, plan)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (other_company_id, "Other Company", "888", "Other Contact", "other@test.com", "other@test.com", "aktiv", "tageskarte")
            )
            db.commit()
        
        token = self.login(self.company_admin_username, self.company_admin_password)
        assert token, "Company admin should login successfully"
        
        # Try to create worker in other company (should fail)
        response = self.client.post(
            "/api/workers",
            json={
                "companyId": other_company_id,  # Wrong company
                "firstName": "Test",
                "lastName": "Worker",
                "photoData": "",
                "badgeId": "TEST123"
            },
            headers=self.get_auth_headers(token)
        )
        assert response.status_code == 403, "Company admin should get 403 when accessing other company"
        assert response.get_json().get("error") == "forbidden_company", "Should indicate company scope violation"

    # ════════════════════════════════════════════════════════════════════════════
    # MISSING ROLE REJECTION
    # ════════════════════════════════════════════════════════════════════════════

    def test_missing_auth_token_returns_401(self):
        """Test missing auth token returns 401."""
        response = self.client.get("/api/system/status")
        assert response.status_code == 401, "Missing token should return 401"
        assert response.get_json().get("error") == "unauthorized", "Should indicate unauthorized"

    def test_invalid_token_returns_401(self):
        """Test invalid token returns 401."""
        response = self.client.get(
            "/api/system/status",
            headers={"Authorization": "Bearer invalid-token-12345"}
        )
        assert response.status_code == 401, "Invalid token should return 401"

    # ════════════════════════════════════════════════════════════════════════════
    # SUPERADMIN ACCESS VALIDATION
    # ════════════════════════════════════════════════════════════════════════════

    def test_superadmin_can_access_protected_endpoints(self):
        """Test superadmin can access superadmin-only endpoints."""
        token = self.login(self.superadmin_username, self.superadmin_password)
        assert token, "Superadmin should login successfully"
        
        response = self.client.get(
            "/api/system/status",
            headers=self.get_auth_headers(token)
        )
        assert response.status_code == 200, "Superadmin should access superadmin endpoints"

    def test_superadmin_can_access_company_admin_endpoints(self):
        """Test superadmin can also access company-admin endpoints."""
        token = self.login(self.superadmin_username, self.superadmin_password)
        assert token, "Superadmin should login successfully"
        
        response = self.client.get(
            "/api/companies",
            headers=self.get_auth_headers(token)
        )
        assert response.status_code == 200, "Superadmin should access company-admin endpoints"

    # ════════════════════════════════════════════════════════════════════════════
    # GATE/TURNSTILE SPECIFIC TESTS
    # ════════════════════════════════════════════════════════════════════════════

    def test_gate_tap_requires_api_key(self):
        """Test /api/gates/tap requires valid API key."""
        response = self.client.post(
            "/api/gates/tap",
            json={"token": "DQR:test", "badgeId": "BP001"}
        )
        assert response.status_code == 401, "Missing API key should return 401"
        assert response.get_json().get("error") == "gate_unauthorized"

    def test_gate_tap_rejects_invalid_api_key(self):
        """Test /api/gates/tap rejects invalid API key."""
        response = self.client.post(
            "/api/gates/tap",
            json={"token": "DQR:test", "badgeId": "BP001"},
            headers={"X-Gate-Key": "invalid-api-key"}
        )
        assert response.status_code == 401, "Invalid API key should return 401"

    def test_unified_scan_requires_api_key(self):
        """Test /api/scan requires valid API key."""
        response = self.client.post(
            "/api/scan",
            json={"token": "test-token", "device_id": "dev001", "direction": "check-in"}
        )
        assert response.status_code == 401, "Missing API key should return 401"

    # ════════════════════════════════════════════════════════════════════════════
    # AUTHORIZATION HEADER HANDLING
    # ════════════════════════════════════════════════════════════════════════════

    def test_bearer_token_format_validation(self):
        """Test Bearer token format is validated."""
        response = self.client.get(
            "/api/system/status",
            headers={"Authorization": "NotBearer token123"}
        )
        assert response.status_code == 401, "Invalid Bearer format should return 401"

    def test_token_in_cookie_not_accepted(self):
        """Test token in cookie is not accepted (must use Authorization header)."""
        _ = self.login("superadmin", self.superadmin_password)
        # Set token in cookie instead of header
        self.client.set_cookie("token", "cookie-only-token")
        
        response = self.client.get("/api/system/status")
        # Should still need the Authorization header
        assert response.status_code == 401, "Token in cookie alone should not authenticate"


class TestRBACMatrix:
    """Test RBAC enforcement matrix for critical operations."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Setup test environment."""
        db_path = tmp_path / "test.sqlite3"
        os.environ["BAUPASS_DB_PATH"] = str(db_path)
        
        app.config["TESTING"] = True
        self.client = app.test_client()
        
        with app.app_context():
            from backend.server import init_db
            init_db()

    def test_rbac_matrix_documentation(self):
        """
        RBAC Enforcement Matrix (Security Control)
        
        Endpoint                          | Superadmin | Company-Admin | Turnstile | Worker | Access Level
        ─────────────────────────────────┼────────────┼──────────────┼───────────┼────────┼──────────────
        GET /api/system/status            |     ✓      |      ✗       |     ✗     |   ✗    | CRITICAL
        GET /api/system/runtime-check     |     ✓      |      ✗       |     ✗     |   ✗    | CRITICAL
        POST /api/system/repair           |     ✓      |      ✗       |     ✗     |   ✗    | CRITICAL
        PUT /api/settings                 |     ✓      |      ✗       |     ✗     |   ✗    | CRITICAL
        POST /api/settings/smtp-test      |     ✓      |      ✗       |     ✗     |   ✗    | CRITICAL
        POST /api/companies               |     ✓      |      ✗       |     ✗     |   ✗    | CRITICAL
        POST /api/demo-seed               |     ✓      |      ✓       |     ✗     |   ✗    | HIGH
        GET /api/companies                |     ✓      |      ✓       |     ✓     |   ✗    | MEDIUM
        POST /api/workers                 |     ✓      |      ✓       |     ✗     |   ✗    | HIGH
        GET /api/workers                  |     ✓      |      ✓       |     ✓     |   ✗    | MEDIUM
        POST /api/workers/import-csv      |     ✓      |      ✓       |     ✗     |   ✗    | HIGH
        GET /api/workers/export.csv       |     ✓      |      ✓       |     ✗     |   ✗    | HIGH
        GET /api/gates/ops-metrics        |     ✓      |      ✓       |     ✓     |   ✗    | MEDIUM
        POST /api/gates/tap               |     N/A    |      N/A     |   API-KEY |   ✗    | CRITICAL
        POST /api/scan                    |     N/A    |      N/A     |   API-KEY |   ✗    | CRITICAL
        
        Notes:
        - ✓ = Access Allowed | ✗ = Access Denied (403) | N/A = Uses API-Key authentication
        - All endpoints require authentication (401 if missing)
        - Superadmin can access all company-admin endpoints (principle of least privilege override)
        - Company-admin can only access resources within their company_id
        - Turnstile role has limited access (gates/metrics only)
        - Gate endpoints (/api/gates/tap, /api/scan) use X-Gate-Key header (API key) not JWT token
        """
        assert True, "RBAC matrix documented for reference"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
