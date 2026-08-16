"""Pytest bootstrap — must run before `import server` in test modules."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BAUPASS_ENV", "testing")
os.environ.setdefault("BAUPASS_ENABLE_BACKGROUND_JOBS", "0")
os.environ.setdefault("BAUPASS_ENABLE_IMAP_POLLER", "0")
os.environ.setdefault("BAUPASS_SKIP_IMAP_POLL", "1")
os.environ.setdefault("BAUPASS_E2E_CHAT_REQUIRED", "1")
os.environ.setdefault("BAUPASS_E2E_ATTACHMENTS_REQUIRED", "1")
os.environ.setdefault("BAUPASS_E2E_SENSITIVE_REQUIRED", "1")

from backend import server  # noqa: E402
from backend.app.runtime_bootstrap import apply_sqlite_migrations  # noqa: E402

TEST_COMPLIANCE_SIGNATURE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAD0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture(autouse=True)
def _reset_server_rate_state():
    server.request_rate_state.clear()
    server.failed_login_attempts.clear()
    yield
    server.request_rate_state.clear()
    server.failed_login_attempts.clear()


@pytest.fixture(autouse=True)
def _restore_db_path_env():
    original_path = server.DB_PATH
    original_env = os.environ.get("BAUPASS_DB_PATH")
    yield
    server.DB_PATH = original_path
    if original_env is None:
        os.environ.pop("BAUPASS_DB_PATH", None)
    else:
        os.environ["BAUPASS_DB_PATH"] = original_env


def _prepare_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import sqlite3

    db_path = tmp_path / "baupass-test.db"
    monkeypatch.setenv("BAUPASS_DB_PATH", str(db_path))
    monkeypatch.setenv("BAUPASS_SQLITE_AUTO_RESTORE", "0")
    monkeypatch.setattr(server, "DB_PATH", db_path)
    server.request_rate_state.clear()
    server.failed_login_attempts.clear()

    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            company_id TEXT,
            twofa_secret TEXT,
            twofa_enabled INTEGER NOT NULL DEFAULT 0,
            api_key_hash TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(company_id) REFERENCES companies(id)
        )
    """)
    conn.execute("""
        CREATE TABLE settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            platform_name TEXT NOT NULL,
            operator_name TEXT NOT NULL,
            turnstile_endpoint TEXT NOT NULL,
            rental_model TEXT NOT NULL,
            monthly_invoice_auto_enabled INTEGER NOT NULL DEFAULT 1,
            monthly_invoice_run_day INTEGER NOT NULL DEFAULT 1,
            monthly_invoice_due_days INTEGER NOT NULL DEFAULT 14,
            invoice_logo_data TEXT NOT NULL DEFAULT '',
            invoice_primary_color TEXT NOT NULL DEFAULT '#06b6d4',
            invoice_accent_color TEXT NOT NULL DEFAULT '#a855f7',
            invoice_iban TEXT NOT NULL DEFAULT '',
            invoice_bic TEXT NOT NULL DEFAULT '',
            invoice_bank_name TEXT NOT NULL DEFAULT '',
            invoice_tax_id TEXT NOT NULL DEFAULT '',
            invoice_vat_id TEXT NOT NULL DEFAULT '',
            invoice_operator_street TEXT NOT NULL DEFAULT '',
            invoice_operator_zip_city TEXT NOT NULL DEFAULT '',
            invoice_operator_phone TEXT NOT NULL DEFAULT '',
            invoice_operator_website TEXT NOT NULL DEFAULT '',
            smtp_host TEXT NOT NULL DEFAULT '',
            smtp_port INTEGER NOT NULL DEFAULT 587,
            smtp_username TEXT NOT NULL DEFAULT '',
            smtp_password TEXT NOT NULL DEFAULT '',
            smtp_sender_email TEXT NOT NULL DEFAULT '',
            smtp_sender_name TEXT NOT NULL DEFAULT 'WorkPass',
            smtp_use_tls INTEGER NOT NULL DEFAULT 1,
            resend_api_key TEXT NOT NULL DEFAULT '',
            resend_from_email TEXT NOT NULL DEFAULT '',
            brevo_api_key TEXT NOT NULL DEFAULT '',
            brevo_from_email TEXT NOT NULL DEFAULT '',
            admin_ip_whitelist TEXT NOT NULL DEFAULT '',
            enforce_admin_ip_whitelist INTEGER NOT NULL DEFAULT 0,
            enforce_tenant_domain INTEGER NOT NULL DEFAULT 0,
            card_print_offset_x_mm REAL NOT NULL DEFAULT 0,
            card_print_offset_y_mm REAL NOT NULL DEFAULT 0,
            card_print_scale_pct REAL NOT NULL DEFAULT 100,
            card_print_rotation_deg REAL NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

    server.init_db()
    apply_sqlite_migrations(db_path)
    server.app.config.update(TESTING=True)
    return db_path


def bootstrap_sqlite_test_db(db_path: Path) -> None:
    """Full schema for unittest modules that manage their own temp DB path."""
    os.environ["BAUPASS_DB_PATH"] = str(db_path)
    os.environ["BAUPASS_SQLITE_AUTO_RESTORE"] = "0"
    server.DB_PATH = db_path
    server.init_db()
    apply_sqlite_migrations(db_path)


@pytest.fixture()
def client_and_db(tmp_path, monkeypatch):
    db_path = _prepare_db(tmp_path, monkeypatch)
    with server.app.test_client() as client:
        yield client, db_path


@pytest.fixture()
def worker_client(tmp_path, monkeypatch):
    # Same clean bootstrap as client_and_db — never auto-restore production backups.
    _prepare_db(tmp_path, monkeypatch)
    with server.app.test_client() as client:
        yield client
