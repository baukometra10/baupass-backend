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

    Migration(
        version="012",
        name="company_site_access_mode",
        up_sql="SELECT 1;",
        down_sql="SELECT 1;",
    ),

    Migration(
        version="013",
        name="platform_api_keys_webhooks_events",
        up_sql="""
            CREATE TABLE IF NOT EXISTS platform_events (
                id              TEXT PRIMARY KEY,
                event_type      TEXT NOT NULL,
                company_id      INTEGER,
                actor_id        TEXT,
                payload_json    TEXT NOT NULL DEFAULT '{}',
                created_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_platform_events_company_ts
                ON platform_events(company_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_platform_events_type_ts
                ON platform_events(event_type, created_at DESC);

            CREATE TABLE IF NOT EXISTS developer_api_keys (
                id                  TEXT PRIMARY KEY,
                company_id          INTEGER NOT NULL,
                name                TEXT NOT NULL,
                key_prefix          TEXT NOT NULL,
                key_hash            TEXT NOT NULL UNIQUE,
                scopes              TEXT NOT NULL DEFAULT 'read',
                status              TEXT NOT NULL DEFAULT 'active',
                created_by_user_id  TEXT,
                created_at          TEXT NOT NULL,
                last_used_at        TEXT,
                expires_at          TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_dev_api_keys_company
                ON developer_api_keys(company_id, status);

            CREATE TABLE IF NOT EXISTS webhook_endpoints (
                id              TEXT PRIMARY KEY,
                company_id      INTEGER NOT NULL,
                url             TEXT NOT NULL,
                secret          TEXT NOT NULL,
                events_json     TEXT NOT NULL DEFAULT '[]',
                status          TEXT NOT NULL DEFAULT 'active',
                created_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_webhook_endpoints_company
                ON webhook_endpoints(company_id, status);

            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                id              TEXT PRIMARY KEY,
                endpoint_id     TEXT NOT NULL,
                company_id      INTEGER NOT NULL,
                event_type      TEXT NOT NULL,
                payload_json    TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                attempt_count   INTEGER NOT NULL DEFAULT 0,
                next_retry_at   TEXT,
                response_status INTEGER,
                response_body   TEXT,
                created_at      TEXT NOT NULL,
                completed_at    TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_pending
                ON webhook_deliveries(company_id, status, next_retry_at);
        """,
        down_sql="""
            DROP TABLE IF EXISTS webhook_deliveries;
            DROP TABLE IF EXISTS webhook_endpoints;
            DROP TABLE IF EXISTS developer_api_keys;
            DROP TABLE IF EXISTS platform_events;
        """,
    ),

    Migration(
        version="014",
        name="enterprise_automation_integrations",
        up_sql="""
            CREATE TABLE IF NOT EXISTS automation_rules (
                id TEXT PRIMARY KEY,
                company_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                trigger_event TEXT NOT NULL DEFAULT '*',
                conditions_json TEXT NOT NULL DEFAULT '[]',
                actions_json TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_automation_rules_company ON automation_rules(company_id, enabled);

            CREATE TABLE IF NOT EXISTS integration_connections (
                id TEXT PRIMARY KEY,
                company_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'connected',
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_integration_company ON integration_connections(company_id, provider);

            CREATE TABLE IF NOT EXISTS company_plugins (
                company_id INTEGER NOT NULL,
                plugin_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                installed_at TEXT NOT NULL,
                PRIMARY KEY (company_id, plugin_id)
            );

            CREATE TABLE IF NOT EXISTS access_permissions (
                id TEXT PRIMARY KEY,
                company_id INTEGER NOT NULL,
                worker_id TEXT,
                zone_id TEXT,
                allowed_from TEXT,
                allowed_until TEXT,
                rules_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_access_perm_company ON access_permissions(company_id);

            CREATE TABLE IF NOT EXISTS emergency_events (
                id TEXT PRIMARY KEY,
                company_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_by TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_emergency_company ON emergency_events(company_id, status);

            CREATE TABLE IF NOT EXISTS document_ocr_results (
                id TEXT PRIMARY KEY,
                company_id INTEGER NOT NULL,
                extracted_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS iot_telemetry (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                received_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_iot_device_ts ON iot_telemetry(device_id, received_at DESC);
        """,
        down_sql="""
            DROP TABLE IF EXISTS iot_telemetry;
            DROP TABLE IF EXISTS document_ocr_results;
            DROP TABLE IF EXISTS emergency_events;
            DROP TABLE IF EXISTS access_permissions;
            DROP TABLE IF EXISTS company_plugins;
            DROP TABLE IF EXISTS integration_connections;
            DROP TABLE IF EXISTS automation_rules;
        """,
    ),

    Migration(
        version="015",
        name="session_devices_and_ai_cache",
        up_sql="""
            CREATE TABLE IF NOT EXISTS session_devices (
                id TEXT PRIMARY KEY,
                session_token_hash TEXT NOT NULL,
                user_id TEXT NOT NULL,
                device_fingerprint TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT '',
                ip_address TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_session_devices_user ON session_devices(user_id, last_seen_at DESC);

            CREATE TABLE IF NOT EXISTS ai_insights_cache (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                insight_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ai_insights_company_type ON ai_insights_cache(company_id, insight_type, expires_at);

            CREATE TABLE IF NOT EXISTS access_logs_archive (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                worker_id TEXT,
                direction TEXT,
                gate TEXT,
                timestamp TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_access_archive_ts ON access_logs_archive(timestamp DESC);
        """,
        down_sql="""
            DROP TABLE IF EXISTS access_logs_archive;
            DROP TABLE IF EXISTS ai_insights_cache;
            DROP TABLE IF EXISTS session_devices;
        """,
    ),

    Migration(
        version="017",
        name="company_data_residency",
        up_sql="""
            CREATE TABLE IF NOT EXISTS company_data_residency (
                company_id INTEGER PRIMARY KEY,
                data_region TEXT NOT NULL DEFAULT '',
                policy TEXT NOT NULL DEFAULT 'default',
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_company_residency_region ON company_data_residency(data_region);
        """,
        down_sql="DROP TABLE IF EXISTS company_data_residency;",
    ),

    Migration(
        version="016",
        name="onboarding_workflows",
        up_sql="""
            CREATE TABLE IF NOT EXISTS onboarding_workflows (
                id TEXT PRIMARY KEY,
                company_id INTEGER NOT NULL,
                worker_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                state_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_onboarding_company_status
                ON onboarding_workflows(company_id, status, updated_at DESC);
        """,
        down_sql="DROP TABLE IF EXISTS onboarding_workflows;",
    ),

    Migration(
        version="018",
        name="physical_operations_os",
        up_sql="""
            ALTER TABLE emergency_events ADD COLUMN emergency_type TEXT NOT NULL DEFAULT 'general';
            ALTER TABLE emergency_events ADD COLUMN site_name TEXT NOT NULL DEFAULT '';

            CREATE TABLE IF NOT EXISTS emergency_roll_calls (
                id TEXT PRIMARY KEY,
                emergency_id TEXT NOT NULL,
                company_id INTEGER NOT NULL,
                worker_id TEXT NOT NULL,
                expected_on_site INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'unknown',
                last_gate TEXT NOT NULL DEFAULT '',
                last_seen_at TEXT,
                marked_at TEXT,
                marked_by TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(emergency_id, worker_id)
            );
            CREATE INDEX IF NOT EXISTS idx_roll_call_emergency ON emergency_roll_calls(emergency_id, status);

            CREATE TABLE IF NOT EXISTS site_equipment (
                id TEXT PRIMARY KEY,
                company_id INTEGER NOT NULL,
                site_name TEXT NOT NULL,
                name TEXT NOT NULL,
                equipment_type TEXT NOT NULL DEFAULT 'machinery',
                latitude REAL,
                longitude REAL,
                status TEXT NOT NULL DEFAULT 'active',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_site_equipment_company ON site_equipment(company_id, site_name);

            CREATE TABLE IF NOT EXISTS site_hazard_zones (
                id TEXT PRIMARY KEY,
                company_id INTEGER NOT NULL,
                site_name TEXT NOT NULL,
                label TEXT NOT NULL,
                hazard_level TEXT NOT NULL DEFAULT 'medium',
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                radius_meters INTEGER NOT NULL DEFAULT 50,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hazard_zones_company ON site_hazard_zones(company_id, active);

            CREATE TABLE IF NOT EXISTS iot_devices (
                id TEXT PRIMARY KEY,
                company_id INTEGER NOT NULL,
                device_type TEXT NOT NULL DEFAULT 'sensor',
                name TEXT NOT NULL,
                site_name TEXT NOT NULL DEFAULT '',
                external_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                config_json TEXT NOT NULL DEFAULT '{}',
                last_seen_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_iot_devices_company ON iot_devices(company_id, device_type);

            CREATE TABLE IF NOT EXISTS worker_reputation_scores (
                worker_id TEXT NOT NULL,
                company_id INTEGER NOT NULL,
                score INTEGER NOT NULL DEFAULT 50,
                grade TEXT NOT NULL DEFAULT 'C',
                breakdown_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (worker_id, company_id)
            );
            CREATE INDEX IF NOT EXISTS idx_reputation_company_score ON worker_reputation_scores(company_id, score DESC);

            CREATE TABLE IF NOT EXISTS security_alerts (
                id TEXT PRIMARY KEY,
                company_id INTEGER NOT NULL,
                worker_id TEXT,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'medium',
                title TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                resolved_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_security_alerts_company ON security_alerts(company_id, status, created_at DESC);

            CREATE TABLE IF NOT EXISTS camera_ai_events (
                id TEXT PRIMARY KEY,
                company_id INTEGER NOT NULL,
                camera_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                worker_id TEXT,
                confidence REAL NOT NULL DEFAULT 0,
                ppe_compliant INTEGER,
                zone_violation INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_camera_events_company ON camera_ai_events(company_id, created_at DESC);
        """,
        down_sql="""
            DROP TABLE IF EXISTS camera_ai_events;
            DROP TABLE IF EXISTS security_alerts;
            DROP TABLE IF EXISTS worker_reputation_scores;
            DROP TABLE IF EXISTS iot_devices;
            DROP TABLE IF EXISTS site_hazard_zones;
            DROP TABLE IF EXISTS site_equipment;
            DROP TABLE IF EXISTS emergency_roll_calls;
        """,
    ),

    Migration(
        version="011",
        name="worker_compliance_indexes",
        up_sql="""
            CREATE INDEX IF NOT EXISTS idx_workers_company_handover
                ON workers(company_id, id_handover_at)
                WHERE deleted_at IS NULL AND id_handover_at IS NOT NULL AND id_handover_at != '';
            CREATE INDEX IF NOT EXISTS idx_workers_active_missing_signature
                ON workers(company_id, status)
                WHERE deleted_at IS NULL
                  AND worker_type = 'worker'
                  AND COALESCE(compliance_signature_data, '') = '';
            CREATE INDEX IF NOT EXISTS idx_access_logs_ts_direction
                ON access_logs(timestamp DESC, direction);
        """,
        down_sql="""
            DROP INDEX IF EXISTS idx_workers_company_handover;
            DROP INDEX IF EXISTS idx_workers_active_missing_signature;
            DROP INDEX IF EXISTS idx_access_logs_ts_direction;
        """,
    ),

]
