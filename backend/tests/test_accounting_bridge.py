"""Tests for external accounting bridge (hours + statements approval)."""
from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path

from backend.app.platform.accounting import auth, hours_service, repository, service
from backend.app.platform.accounting.monthly_job import previous_period, run_monthly_accounting_exports
from backend.app.platform.accounting.schema import ensure_accounting_schema


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_accounting_schema(conn)
    conn.execute(
        """
        CREATE TABLE companies (
            id TEXT PRIMARY KEY, name TEXT, deleted_at TEXT,
            workpass_lohn_enabled INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE workers (
            id TEXT PRIMARY KEY, company_id TEXT, first_name TEXT, last_name TEXT,
            badge_id TEXT, insurance_number TEXT, status TEXT, deleted_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id TEXT, direction TEXT, timestamp TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE employment_contracts (
            id TEXT PRIMARY KEY, company_id TEXT, worker_id TEXT, status TEXT,
            input_json TEXT, updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE worker_documents (
            id TEXT PRIMARY KEY, worker_id TEXT, company_id TEXT, doc_type TEXT,
            filename TEXT, file_path TEXT, file_size INTEGER,
            source_email_from TEXT, source_inbox_id TEXT, uploaded_by_user_id TEXT,
            created_at TEXT, notes TEXT
        )
        """
    )
    conn.execute("INSERT INTO companies (id, name) VALUES ('c1', 'Demo GmbH')")
    conn.execute(
        """
        INSERT INTO workers (id, company_id, first_name, last_name, badge_id, insurance_number, status, deleted_at)
        VALUES ('w1', 'c1', 'Ali', 'Hassan', 'B1', '', 'active', NULL)
        """
    )
    conn.execute(
        """
        INSERT INTO employment_contracts (id, company_id, worker_id, status, input_json, updated_at)
        VALUES ('ctr1', 'c1', 'w1', 'signed', ?, '2026-06-01T00:00:00Z')
        """,
        (json.dumps({"hourly_rate": "15.00"}),),
    )
    conn.execute(
        "INSERT INTO access_logs (worker_id, direction, timestamp) VALUES ('w1', 'check-in', '2026-06-02T08:00:00')"
    )
    conn.execute(
        "INSERT INTO access_logs (worker_id, direction, timestamp) VALUES ('w1', 'check-out', '2026-06-02T16:00:00')"
    )
    conn.commit()
    return conn


def test_hours_from_access_pairs():
    hours = hours_service.hours_from_access_pairs(
        [
            {"direction": "check-in", "timestamp": "2026-06-01T08:00:00"},
            {"direction": "check-out", "timestamp": "2026-06-01T12:00:00"},
            {"direction": "check-in", "timestamp": "2026-06-01T13:00:00"},
            {"direction": "check-out", "timestamp": "2026-06-01T17:00:00"},
        ]
    )
    assert hours == 8.0


def test_aggregate_company_hours_with_rate():
    db = _db()
    payload = hours_service.aggregate_company_hours(db, company_id="c1", period="2026-06")
    assert payload["rowCount"] == 1
    row = payload["rows"][0]
    assert row["hours"] == 8.0
    assert row["hourlyRate"] == 15.0
    assert row["grossEstimate"] == 120.0


def test_hmac_sign_verify():
    secret = "test-secret"
    body = b'{"ok":true}'
    ts = "1700000000"
    sig = auth.sign_payload(secret, timestamp=ts, body=body)
    assert auth.verify_signature(secret, timestamp=ts, body=body, signature=sig, max_skew_seconds=10**9)


def test_integration_and_hour_export_ack():
    db = _db()
    created = repository.upsert_integration(db, company_id="c1", webhook_url="", rotate_key=True)
    assert created.get("apiKey", "").startswith("acc_live_")
    payload = service.prepare_hour_export(db, company_id="c1", period="2026-06", mark_sent=True)
    assert payload["exportId"]
    ack = repository.ack_hour_export(
        db, company_id="c1", period="2026-06", fingerprint=payload["fingerprint"]
    )
    assert ack["ok"] is True


def test_ingest_and_approve_releases_document(tmp_path, monkeypatch):
    db = _db()
    repository.upsert_integration(db, company_id="c1", rotate_key=True)
    pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    monkeypatch.setattr(
        service,
        "_storage_dir",
        lambda company_id, period: Path(tmp_path) / company_id / period,
    )
    notified = []

    def _fake_notify(db_, worker_id, filename, *, doc_type="lohnabrechnung"):
        notified.append((worker_id, filename, doc_type))

    monkeypatch.setattr("backend.server._notify_worker_payroll_document", _fake_notify, raising=False)
    # Patch import path used inside approve_batch
    import backend.server as server_mod

    monkeypatch.setattr(server_mod, "_notify_worker_payroll_document", _fake_notify, raising=False)

    result = service.ingest_statements(
        db,
        company_id="c1",
        period="2026-06",
        statements=[
            {
                "workerId": "w1",
                "companyId": "c1",
                "employeeId": "w1",
                "hours": 8,
                "hourlyRate": 15,
                "grossAmount": 120,
                "netAmount": 95,
                "pdfBase64": base64.b64encode(pdf).decode("ascii"),
                "filename": "lohn_w1.pdf",
            }
        ],
    )
    assert result["ok"] is True
    batch_id = result["batchId"]
    approved = service.approve_batch(db, batch_id=batch_id, actor_user_id="admin-1")
    assert approved["ok"] is True
    assert approved["released"] == 1
    doc = db.execute("SELECT doc_type, worker_id FROM worker_documents").fetchone()
    assert doc["doc_type"] == "lohnabrechnung"
    assert doc["worker_id"] == "w1"
    assert notified


def test_reject_batch_no_release(tmp_path, monkeypatch):
    db = _db()
    pdf = b"%PDF-1.4 fake\n%%EOF\n"
    monkeypatch.setattr(
        service,
        "_storage_dir",
        lambda company_id, period: Path(tmp_path) / company_id / period,
    )
    # minimal valid-ish pdf header for ingest
    pdf = b"%PDF-1.4\n%%EOF\n"
    result = service.ingest_statements(
        db,
        company_id="c1",
        period="2026-06",
        statements=[{"workerId": "w1", "companyId": "c1", "hours": 1, "pdfBase64": base64.b64encode(pdf).decode("ascii")}],
    )
    rejected = service.reject_batch(db, batch_id=result["batchId"], actor_user_id="admin-1", reason="wrong")
    assert rejected["ok"] is True
    assert db.execute("SELECT COUNT(*) AS c FROM worker_documents").fetchone()["c"] == 0


def test_previous_period():
    from datetime import datetime, timezone

    assert previous_period(datetime(2026, 7, 1, tzinfo=timezone.utc)) == "2026-06"
    assert previous_period(datetime(2026, 1, 5, tzinfo=timezone.utc)) == "2025-12"


def test_tenant_storage_keys_isolate_same_employee_number():
    from backend.app.platform.accounting.keys import invoice_storage_key, payroll_storage_key

    a = payroll_storage_key(company_id="lufthansa", employee_id="1001", period="2026-06")
    b = payroll_storage_key(company_id="otherco", employee_id="1001", period="2026-06")
    assert a == "lufthansa::1001::2026-06"
    assert b == "otherco::1001::2026-06"
    assert a != b
    assert invoice_storage_key(company_id="lufthansa", invoice_number="RE-1") == "lufthansa::RE-1"
    assert invoice_storage_key(company_id="otherco", invoice_number="RE-1") == "otherco::RE-1"


def test_hours_rows_include_storage_key():
    db = _db()
    payload = hours_service.aggregate_company_hours(db, company_id="c1", period="2026-06")
    row = payload["rows"][0]
    assert row["storageKey"] == "c1::w1::2026-06"
    assert row["company"]["id"] == "c1"
    assert payload["company"]["id"] == "c1"


def test_ingest_rejects_missing_company_id_on_row():
    db = _db()
    result = service.ingest_statements(
        db,
        company_id="c1",
        period="2026-06",
        statements=[{"workerId": "w1", "hours": 1}],
    )
    assert result["createdCount"] == 0
    assert result["errors"][0]["error"] == "company_id_required"


def test_auto_provision_skipped_when_link_disabled():
    from backend.app.platform.accounting.platform_link import auto_provision_if_enabled, save_platform_link

    db = _db()
    save_platform_link(db, enabled=False, base_url="https://lohn.test", master_api_key="master")
    out = auto_provision_if_enabled(db, "c1")
    assert out.get("skipped") == "platform_link_disabled"


def test_provision_creates_local_integration_and_posts(monkeypatch):
    from backend.app.platform.accounting import platform_link
    from backend.app.platform.accounting.company_opt_in import set_workpass_lohn_enabled

    db = _db()
    db.execute(
        "CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT, role TEXT, company_id TEXT)"
    )
    db.execute(
        "INSERT INTO users (id, username, role, company_id) VALUES ('u1', 'demofirma', 'company-admin', 'c1')"
    )
    # Opt-in first (optional feature)
    set_workpass_lohn_enabled(db, "c1", enabled=True, provision_if_enabled=False)
    platform_link.save_platform_link(
        db,
        enabled=True,
        base_url="https://lohn.test",
        master_api_key="master-secret",
        platform_public_url="https://platform.test",
        auto_provision=True,
    )
    calls = []

    def _fake_post(link, body):
        calls.append(body)
        return {"ok": True, "status": 200, "body": "{}"}

    monkeypatch.setattr(platform_link, "_post_lohn_upsert", _fake_post)
    result = platform_link.provision_company_for_lohn(
        db,
        "c1",
        force=True,
        admin_username="demofirma",
        admin_password="Secret123!",
    )
    assert result["ok"] is True
    assert calls
    assert calls[0]["id"] == "c1"
    assert calls[0]["platformBridge"]["accountingKey"].startswith("acc_live_")
    assert calls[0]["platformBridge"]["firmaId"] == "c1"
    assert calls[0]["platformBridge"]["accessUrl"].endswith("/api/v2/accounting/company/access")
    assert calls[0]["access"]["username"] == "demofirma"
    assert calls[0]["access"]["password"] == "Secret123!"
    assert calls[0]["login"]["password"] == "Secret123!"
    integ = repository.get_integration(db, "c1")
    assert integ is not None
    assert int(integ["enabled"]) == 1
    login = repository.get_lohn_login(db, "c1")
    assert login == {"username": "demofirma", "password": "Secret123!"}


def test_company_access_login_roundtrip():
    db = _db()
    repository.upsert_integration(db, company_id="c1", webhook_url="", rotate_key=True)
    assert repository.store_lohn_login(db, "c1", username="acme", password="Pw-42")["ok"] is True
    login = repository.get_lohn_login(db, "c1")
    assert login["username"] == "acme"
    assert login["password"] == "Pw-42"


def test_disable_stops_outbound(monkeypatch):
    from backend.app.platform.accounting.company_opt_in import set_workpass_lohn_enabled
    from backend.app.platform.accounting import service as accounting_service

    db = _db()
    set_workpass_lohn_enabled(db, "c1", enabled=True, provision_if_enabled=False)
    repository.upsert_integration(db, company_id="c1", webhook_url="https://lohn.test/hook", rotate_key=True)
    set_workpass_lohn_enabled(db, "c1", enabled=False, provision_if_enabled=False)
    out = accounting_service.notify_hours_ready(db, company_id="c1", period="2026-06")
    assert out.get("error") == "workpass_lohn_disabled"
    integ = repository.get_integration(db, "c1")
    assert int(integ["enabled"]) == 0


def test_monthly_job_skips_wrong_day():
    from backend.app.platform.accounting.company_opt_in import set_workpass_lohn_enabled

    db = _db()
    set_workpass_lohn_enabled(db, "c1", enabled=True, provision_if_enabled=False)
    repository.upsert_integration(db, company_id="c1", run_day=1, rotate_key=True)
    from datetime import datetime, timezone

    out = run_monthly_accounting_exports(
        db, reference_date=datetime(2026, 7, 15, tzinfo=timezone.utc), force=False
    )
    assert out["results"][0].get("skipped") == "not_run_day"
