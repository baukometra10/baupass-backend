"""Schema for external accounting bridge (company-isolated)."""
from __future__ import annotations

_ENSURED = False


def ensure_accounting_schema(db) -> None:
    global _ENSURED
    # Always idempotent CREATE IF NOT EXISTS; skip only after success in-process.
    statements = (
        """
        CREATE TABLE IF NOT EXISTS accounting_integrations (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            webhook_url TEXT NOT NULL DEFAULT '',
            api_key_hash TEXT NOT NULL DEFAULT '',
            api_key_prefix TEXT NOT NULL DEFAULT '',
            signing_secret TEXT NOT NULL DEFAULT '',
            run_day INTEGER NOT NULL DEFAULT 1,
            last_export_period TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS payroll_hour_exports (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            period TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            payload_json TEXT NOT NULL DEFAULT '{}',
            fingerprint TEXT NOT NULL DEFAULT '',
            row_count INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            sent_at TEXT,
            acked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(company_id, period)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS payroll_statement_batches (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            period TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_approval',
            source TEXT NOT NULL DEFAULT 'accounting_app',
            external_ref TEXT NOT NULL DEFAULT '',
            statement_count INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            approved_at TEXT,
            approved_by_user_id TEXT,
            rejected_at TEXT,
            rejected_by_user_id TEXT,
            released_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS payroll_statements (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            worker_id TEXT NOT NULL,
            period TEXT NOT NULL,
            hours REAL NOT NULL DEFAULT 0,
            hourly_rate REAL NOT NULL DEFAULT 0,
            gross_amount REAL NOT NULL DEFAULT 0,
            net_amount REAL,
            currency TEXT NOT NULL DEFAULT 'EUR',
            filename TEXT NOT NULL DEFAULT '',
            file_path TEXT NOT NULL DEFAULT '',
            file_size INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            worker_document_id TEXT,
            external_ref TEXT NOT NULL DEFAULT '',
            meta_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_accounting_integrations_company ON accounting_integrations(company_id)",
        "CREATE INDEX IF NOT EXISTS idx_payroll_hour_exports_company_period ON payroll_hour_exports(company_id, period)",
        "CREATE INDEX IF NOT EXISTS idx_payroll_batches_company_status ON payroll_statement_batches(company_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_payroll_statements_batch ON payroll_statements(batch_id)",
        "CREATE INDEX IF NOT EXISTS idx_payroll_statements_worker ON payroll_statements(worker_id, period)",
        """
        CREATE TABLE IF NOT EXISTS lohn_data_alerts (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            worker_id TEXT NOT NULL DEFAULT '',
            employee_id TEXT NOT NULL DEFAULT '',
            period TEXT NOT NULL DEFAULT '',
            missing_fields_json TEXT NOT NULL DEFAULT '[]',
            message TEXT NOT NULL DEFAULT '',
            external_ref TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            dismissed_at TEXT,
            dismissed_by_user_id TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_lohn_data_alerts_company_status ON lohn_data_alerts(company_id, status)",
        """
        CREATE TABLE IF NOT EXISTS accounting_messages (
            id TEXT PRIMARY KEY,
            external_id TEXT NOT NULL DEFAULT '',
            company_id TEXT NOT NULL,
            event TEXT NOT NULL DEFAULT 'accounting.message',
            kind TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            period TEXT NOT NULL DEFAULT '',
            worker_id TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            received_at TEXT NOT NULL,
            read_at TEXT,
            acked_at TEXT,
            ack_error TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(company_id, external_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_accounting_messages_company_status ON accounting_messages(company_id, status)",
        """
        CREATE TABLE IF NOT EXISTS lohn_period_requests (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            period TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_confirmation',
            source TEXT NOT NULL DEFAULT 'lohn',
            want_employees INTEGER NOT NULL DEFAULT 1,
            want_payroll INTEGER NOT NULL DEFAULT 1,
            note TEXT NOT NULL DEFAULT '',
            external_ref TEXT NOT NULL DEFAULT '',
            employee_count INTEGER NOT NULL DEFAULT 0,
            total_hours REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            confirmed_at TEXT,
            confirmed_by_user_id TEXT,
            rejected_at TEXT,
            rejected_by_user_id TEXT,
            reject_reason TEXT NOT NULL DEFAULT '',
            delivered_at TEXT,
            delivery_error TEXT NOT NULL DEFAULT '',
            UNIQUE(company_id, period)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_lohn_period_requests_company_status ON lohn_period_requests(company_id, status)",
    )
    for sql in statements:
        db.execute(sql)
    _ensure_integration_login_columns(db)
    _ensure_accounting_message_banner_column(db)
    try:
        db.commit()
    except Exception:
        pass
    _ENSURED = True


def _ensure_accounting_message_banner_column(db) -> None:
    """Banner dismiss ≠ inbox read — like phone notification vs Gmail unread."""
    cols: set[str] = set()
    try:
        cols = {str(r[1]) for r in db.execute("PRAGMA table_info(accounting_messages)").fetchall()}
    except Exception:
        cols = set()
    if cols and "banner_dismissed_at" not in cols:
        try:
            db.execute("ALTER TABLE accounting_messages ADD COLUMN banner_dismissed_at TEXT")
        except Exception:
            pass
    elif not cols:
        try:
            db.execute(
                "ALTER TABLE accounting_messages ADD COLUMN IF NOT EXISTS banner_dismissed_at TEXT"
            )
        except Exception:
            pass


def _ensure_integration_login_columns(db) -> None:
    """Store company-admin login for WorkPass Lohn bridge (encrypted at rest when key set)."""
    cols: set[str] = set()
    try:
        cols = {str(r[1]) for r in db.execute("PRAGMA table_info(accounting_integrations)").fetchall()}
    except Exception:
        cols = set()
    alters = []
    if cols:
        if "lohn_login_username" not in cols:
            alters.append(
                "ALTER TABLE accounting_integrations ADD COLUMN lohn_login_username TEXT NOT NULL DEFAULT ''"
            )
        if "lohn_login_password_enc" not in cols:
            alters.append(
                "ALTER TABLE accounting_integrations ADD COLUMN lohn_login_password_enc TEXT NOT NULL DEFAULT ''"
            )
    else:
        # Postgres / unknown: best-effort IF NOT EXISTS style
        alters = [
            "ALTER TABLE accounting_integrations ADD COLUMN IF NOT EXISTS lohn_login_username TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE accounting_integrations ADD COLUMN IF NOT EXISTS lohn_login_password_enc TEXT NOT NULL DEFAULT ''",
        ]
    for sql in alters:
        try:
            db.execute(sql)
        except Exception:
            pass
