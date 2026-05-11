"""
BauPass – Database Migrations Registry
========================================
Schema الفعلي (baupass.db):
  - workers: id, company_id, badge_id, badge_id_lookup, contact_email, status, deleted_at
  - access_logs: id, worker_id, direction, gate, note, timestamp, checked_in_late
  - worker_documents: id, worker_id, company_id, doc_type, expiry_date, created_at
  - invoices: id, company_id, status, due_date, next_retry_at, invoice_date
  - audit_logs: id, event_type, actor_user_id, company_id, created_at
  - devices: id, company_id, device_type, api_key_hash
  - device_ingest_events: id, company_id, device_id, employee_id, received_at
"""
from __future__ import annotations

from backend.app.database import Migration

ALL_MIGRATIONS: list[Migration] = [

    Migration(
        version="001",
        name="migration_tracking_bootstrap",
        up_sql="SELECT 1;",
        down_sql="SELECT 1;",
    ),

    Migration(
        version="002",
        name="core_schema_indexes",
        up_sql="""
            CREATE INDEX IF NOT EXISTS idx_workers_company_id ON workers(company_id);
            CREATE INDEX IF NOT EXISTS idx_workers_badge_id ON workers(badge_id);
            CREATE INDEX IF NOT EXISTS idx_workers_company_status ON workers(company_id, status);
            CREATE INDEX IF NOT EXISTS idx_workers_contact_email ON workers(contact_email) WHERE contact_email IS NOT NULL AND contact_email != '';
            CREATE INDEX IF NOT EXISTS idx_workers_badge_lookup ON workers(badge_id_lookup) WHERE badge_id_lookup IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_workers_not_deleted ON workers(company_id, status) WHERE deleted_at IS NULL;
            CREATE INDEX IF NOT EXISTS idx_access_logs_worker_ts ON access_logs(worker_id, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_access_logs_gate_ts ON access_logs(gate, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_worker_docs_company_expires ON worker_documents(company_id, expiry_date) WHERE expiry_date IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_worker_docs_worker_id ON worker_documents(worker_id);
            CREATE INDEX IF NOT EXISTS idx_invoices_company_date ON invoices(company_id, invoice_date DESC);
            CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
            CREATE INDEX IF NOT EXISTS idx_invoices_due_date ON invoices(due_date) WHERE status IN ('sent', 'overdue');
            CREATE INDEX IF NOT EXISTS idx_invoices_next_retry ON invoices(next_retry_at) WHERE next_retry_at IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_audit_logs_company_created ON audit_logs(company_id, created_at DESC) WHERE company_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs(event_type, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor_user_id) WHERE actor_user_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_devices_company ON devices(company_id);
            CREATE INDEX IF NOT EXISTS idx_devices_company_type ON devices(company_id, device_type);
            CREATE INDEX IF NOT EXISTS idx_device_events_company_ts ON device_ingest_events(company_id, received_at DESC);
            CREATE INDEX IF NOT EXISTS idx_device_events_device_ts ON device_ingest_events(device_id, received_at DESC);
            CREATE INDEX IF NOT EXISTS idx_device_events_employee ON device_ingest_events(employee_id, received_at DESC) WHERE employee_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_leave_requests_worker ON leave_requests(worker_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_leave_requests_company_status ON leave_requests(company_id, status);
            CREATE INDEX IF NOT EXISTS idx_worker_passes_worker_platform ON worker_passes(worker_id, platform);
            CREATE INDEX IF NOT EXISTS idx_worker_passes_company_status ON worker_passes(company_id, status);
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
            CREATE INDEX IF NOT EXISTS idx_wit_company ON worker_identity_tokens(company_id, status);
            CREATE INDEX IF NOT EXISTS idx_wit_token_hash ON worker_identity_tokens(token_hash) WHERE status = 'active';
            CREATE INDEX IF NOT EXISTS idx_system_alerts_resolved ON system_alerts(resolved_at, created_at DESC);
        """,
        down_sql="""
            DROP INDEX IF EXISTS idx_workers_company_id;
            DROP INDEX IF EXISTS idx_workers_badge_id;
            DROP INDEX IF EXISTS idx_workers_company_status;
            DROP INDEX IF EXISTS idx_workers_contact_email;
            DROP INDEX IF EXISTS idx_workers_badge_lookup;
            DROP INDEX IF EXISTS idx_workers_not_deleted;
            DROP INDEX IF EXISTS idx_access_logs_worker_ts;
            DROP INDEX IF EXISTS idx_access_logs_gate_ts;
            DROP INDEX IF EXISTS idx_worker_docs_company_expires;
            DROP INDEX IF EXISTS idx_worker_docs_worker_id;
            DROP INDEX IF EXISTS idx_invoices_company_date;
            DROP INDEX IF EXISTS idx_invoices_status;
            DROP INDEX IF EXISTS idx_invoices_due_date;
            DROP INDEX IF EXISTS idx_invoices_next_retry;
            DROP INDEX IF EXISTS idx_audit_logs_company_created;
            DROP INDEX IF EXISTS idx_audit_logs_event_type;
            DROP INDEX IF EXISTS idx_audit_logs_actor;
            DROP INDEX IF EXISTS idx_devices_company;
            DROP INDEX IF EXISTS idx_devices_company_type;
            DROP INDEX IF EXISTS idx_device_events_company_ts;
            DROP INDEX IF EXISTS idx_device_events_device_ts;
            DROP INDEX IF EXISTS idx_device_events_employee;
            DROP INDEX IF EXISTS idx_leave_requests_worker;
            DROP INDEX IF EXISTS idx_leave_requests_company_status;
            DROP INDEX IF EXISTS idx_worker_passes_worker_platform;
            DROP INDEX IF EXISTS idx_worker_passes_company_status;
            DROP INDEX IF EXISTS idx_sessions_user_id;
            DROP INDEX IF EXISTS idx_sessions_expires;
            DROP INDEX IF EXISTS idx_wit_company;
            DROP INDEX IF EXISTS idx_wit_token_hash;
            DROP INDEX IF EXISTS idx_system_alerts_resolved;
        """,
    ),

    Migration(
        version="003",
        name="security_events_table",
        up_sql="""
            CREATE TABLE IF NOT EXISTS security_events (
                id          TEXT PRIMARY KEY,
                event_type  TEXT NOT NULL,
                severity    TEXT NOT NULL DEFAULT 'info',
                company_id  INTEGER,
                actor_id    TEXT,
                ip_address  TEXT,
                user_agent  TEXT,
                details     TEXT,
                created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                request_id  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_security_events_company ON security_events(company_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_security_events_type ON security_events(event_type, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_security_events_ip ON security_events(ip_address, created_at DESC);
        """,
        down_sql="DROP TABLE IF EXISTS security_events;",
    ),

    Migration(
        version="004",
        name="rate_limit_bans_table",
        up_sql="""
            CREATE TABLE IF NOT EXISTS rate_limit_bans (
                id          TEXT PRIMARY KEY,
                ip_address  TEXT NOT NULL UNIQUE,
                reason      TEXT NOT NULL,
                banned_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                expires_at  TEXT NOT NULL,
                lifted_at   TEXT,
                lift_reason TEXT,
                created_by  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_rate_bans_ip ON rate_limit_bans(ip_address, expires_at) WHERE lifted_at IS NULL;
        """,
        down_sql="DROP TABLE IF EXISTS rate_limit_bans;",
    ),

    Migration(
        version="005",
        name="anti_replay_scan_nonces",
        up_sql="""
            CREATE TABLE IF NOT EXISTS scan_nonces (
                nonce       TEXT PRIMARY KEY,
                used_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                expires_at  TEXT NOT NULL,
                device_id   TEXT,
                company_id  INTEGER,
                purpose     TEXT NOT NULL DEFAULT 'scan'
            );
            CREATE INDEX IF NOT EXISTS idx_scan_nonces_expires ON scan_nonces(expires_at);
        """,
        down_sql="DROP TABLE IF EXISTS scan_nonces;",
    ),

    Migration(
        version="006",
        name="feature_flags_system",
        up_sql="""
            CREATE TABLE IF NOT EXISTS feature_flags (
                id                  TEXT PRIMARY KEY,
                flag_key            TEXT NOT NULL UNIQUE,
                description         TEXT NOT NULL,
                enabled_global      INTEGER NOT NULL DEFAULT 0,
                rollout_pct         INTEGER NOT NULL DEFAULT 0,
                enabled_companies   TEXT DEFAULT '[]',
                disabled_companies  TEXT DEFAULT '[]',
                created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_by          TEXT
            );
            INSERT OR IGNORE INTO feature_flags (id, flag_key, description, enabled_global) VALUES
                ('ff_wallet',    'wallet_passes',    'Apple/Google Wallet passes', 0),
                ('ff_realtime',  'realtime_ws',      'WebSocket realtime updates', 0),
                ('ff_offline',   'offline_gates',    'Offline gate operation mode', 0),
                ('ff_gdpr',      'gdpr_data_export', 'GDPR data export for workers', 1),
                ('ff_analytics', 'advanced_reports', 'Advanced analytics dashboard', 0),
                ('ff_apiv2',     'api_v2',           'API v2 endpoints', 0);
        """,
        down_sql="DROP TABLE IF EXISTS feature_flags;",
    ),

    Migration(
        version="007",
        name="gdpr_compliance_tables",
        up_sql="""
            CREATE TABLE IF NOT EXISTS gdpr_requests (
                id              TEXT PRIMARY KEY,
                request_type    TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                requester_type  TEXT NOT NULL,
                requester_id    TEXT NOT NULL,
                company_id      INTEGER NOT NULL,
                worker_id       TEXT,
                submitted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                completed_at    TEXT,
                expires_at      TEXT,
                notes           TEXT,
                processed_by    TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_gdpr_requests_company ON gdpr_requests(company_id, submitted_at DESC);
            CREATE INDEX IF NOT EXISTS idx_gdpr_requests_status ON gdpr_requests(status) WHERE status = 'pending';

            CREATE TABLE IF NOT EXISTS data_consents (
                id              TEXT PRIMARY KEY,
                worker_id       TEXT NOT NULL,
                company_id      INTEGER NOT NULL,
                consent_type    TEXT NOT NULL,
                granted         INTEGER NOT NULL DEFAULT 0,
                granted_at      TEXT,
                revoked_at      TEXT,
                ip_address      TEXT,
                version         TEXT NOT NULL DEFAULT '1.0'
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_data_consents_worker_type ON data_consents(worker_id, consent_type);
        """,
        down_sql="""
            DROP TABLE IF EXISTS gdpr_requests;
            DROP TABLE IF EXISTS data_consents;
        """,
    ),

    Migration(
        version="008",
        name="background_task_audit",
        up_sql="""
            CREATE TABLE IF NOT EXISTS task_executions (
                id              TEXT PRIMARY KEY,
                task_name       TEXT NOT NULL,
                queue_name      TEXT NOT NULL DEFAULT 'default',
                status          TEXT NOT NULL DEFAULT 'pending',
                company_id      INTEGER,
                idempotency_key TEXT UNIQUE,
                enqueued_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                started_at      TEXT,
                completed_at    TEXT,
                attempt_count   INTEGER NOT NULL DEFAULT 0,
                last_error      TEXT,
                result_summary  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_task_exec_company ON task_executions(company_id, enqueued_at DESC) WHERE company_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_task_exec_status ON task_executions(status, enqueued_at DESC);
            CREATE INDEX IF NOT EXISTS idx_task_exec_idem ON task_executions(idempotency_key) WHERE idempotency_key IS NOT NULL;
        """,
        down_sql="DROP TABLE IF EXISTS task_executions;",
    ),

    Migration(
        version="009",
        name="immutable_signed_audit_chain",
        up_sql="""
            CREATE TABLE IF NOT EXISTS immutable_audit_events (
                seq             INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id        TEXT NOT NULL UNIQUE,
                event_type      TEXT NOT NULL,
                company_id      INTEGER,
                actor_id        TEXT,
                request_id      TEXT,
                source          TEXT NOT NULL DEFAULT 'api',
                occurred_at     TEXT NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                payload_json    TEXT NOT NULL,
                prev_hash       TEXT,
                event_hash      TEXT NOT NULL UNIQUE,
                signature       TEXT NOT NULL,
                key_id          TEXT NOT NULL DEFAULT 'v1',
                idempotency_key TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_imm_audit_created ON immutable_audit_events(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_imm_audit_company ON immutable_audit_events(company_id, created_at DESC) WHERE company_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_imm_audit_type ON immutable_audit_events(event_type, created_at DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_imm_audit_idem ON immutable_audit_events(idempotency_key) WHERE idempotency_key IS NOT NULL;

            CREATE TRIGGER IF NOT EXISTS trg_imm_audit_no_update
            BEFORE UPDATE ON immutable_audit_events
            BEGIN
                SELECT RAISE(ABORT, 'immutable_audit_events is append-only');
            END;

            CREATE TRIGGER IF NOT EXISTS trg_imm_audit_no_delete
            BEFORE DELETE ON immutable_audit_events
            BEGIN
                SELECT RAISE(ABORT, 'immutable_audit_events is append-only');
            END;
        """,
        down_sql="""
            DROP TRIGGER IF EXISTS trg_imm_audit_no_update;
            DROP TRIGGER IF EXISTS trg_imm_audit_no_delete;
            DROP TABLE IF EXISTS immutable_audit_events;
        """,
    ),

    Migration(
        version="010",
        name="idempotency_operation_keys",
        up_sql="""
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id          INTEGER,
                scope               TEXT NOT NULL,
                idempotency_key     TEXT NOT NULL,
                status              TEXT NOT NULL DEFAULT 'processing',
                request_hash        TEXT,
                response_json       TEXT,
                created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                completed_at        TEXT,
                expires_at          TEXT,
                UNIQUE(company_id, scope, idempotency_key)
            );

            CREATE INDEX IF NOT EXISTS idx_idem_scope_created ON idempotency_keys(scope, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_idem_company_scope ON idempotency_keys(company_id, scope, created_at DESC) WHERE company_id IS NOT NULL;
        """,
        down_sql="DROP TABLE IF EXISTS idempotency_keys;",
    ),

]
