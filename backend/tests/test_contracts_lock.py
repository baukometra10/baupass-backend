"""Contracts owner lock via SMS/email OTP."""
from __future__ import annotations


def _superadmin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def _create_company(client, headers, name: str) -> str:
    response = client.post(
        "/api/companies",
        json={
            "name": name,
            "contact": "x",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 0,
        },
        headers=headers,
    )
    assert response.status_code in (200, 201)
    payload = response.get_json() or {}
    company = payload.get("company") or {}
    return str(company.get("id") or payload.get("id") or "")


def test_contracts_open_without_owner_phone(client_and_db):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "OpenContractsCo")
    status = client.get(f"/api/contracts/lock-status?company_id={company_id}", headers=headers)
    assert status.status_code == 200
    body = status.get_json()
    assert body["lockRequired"] is False
    assert body["unlocked"] is True
    templates = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    assert templates.status_code == 200


def test_contracts_lock_otp_flow(client_and_db, monkeypatch):
    client, _db_path = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "LockedContractsCo")

    monkeypatch.setenv("BAUPASS_ENV", "testing")
    monkeypatch.setattr(
        "backend.app.platform.security.contracts_lock._OTP_REQUEST_MIN_SECONDS",
        0,
    )
    monkeypatch.setattr(
        "backend.app.platform.security.contracts_lock._OTP_REQUEST_MAX_PER_HOUR",
        100,
    )

    req = client.post(
        "/api/contracts/lock/request-otp",
        json={"company_id": company_id, "setup": True, "phone": "+491701234567", "email": "owner@example.com"},
        headers=headers,
    )
    assert req.status_code == 200, req.get_json()
    code = (req.get_json() or {}).get("debugCode")
    assert code

    # Still open until phone is verified/saved
    open_before = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    assert open_before.status_code == 200

    verify = client.post(
        "/api/contracts/lock/verify",
        json={
            "company_id": company_id,
            "setup": True,
            "phone": "+491701234567",
            "email": "owner@example.com",
            "code": code,
        },
        headers=headers,
    )
    assert verify.status_code == 200, verify.get_json()
    assert verify.get_json().get("unlocked") is True

    # Relock
    locked = client.post(
        "/api/contracts/lock",
        json={"company_id": company_id},
        headers=headers,
    )
    assert locked.status_code == 200

    soft = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    assert soft.status_code == 200

    listed = client.get(f"/api/contracts?company_id={company_id}", headers=headers)
    assert listed.status_code == 200
    assert listed.get_json().get("salaryRedacted") is True

    # Request + verify again
    req2 = client.post(
        "/api/contracts/lock/request-otp",
        json={"company_id": company_id},
        headers=headers,
    )
    assert req2.status_code == 200
    code2 = (req2.get_json() or {}).get("debugCode")
    assert code2
    verify2 = client.post(
        "/api/contracts/lock/verify",
        json={"company_id": company_id, "code": code2},
        headers=headers,
    )
    assert verify2.status_code == 200
    ok_again = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    assert ok_again.status_code == 200


def test_contracts_otp_persists_hashed_in_db(client_and_db, monkeypatch):
    client, db_path = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "PersistOtpCo")
    monkeypatch.setenv("BAUPASS_ENV", "testing")

    req = client.post(
        "/api/contracts/lock/request-otp",
        json={"company_id": company_id, "setup": True, "phone": "+491701111111", "email": "a@example.com"},
        headers=headers,
    )
    assert req.status_code == 200
    code = (req.get_json() or {}).get("debugCode")
    assert code

    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT code_hash, expires_at FROM step_up_otps WHERE purpose = 'owner' AND company_id = ?",
        (company_id,),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["code_hash"]
    assert str(code) != str(row["code_hash"])


def test_owner_step_up_blocks_worker_export(client_and_db, monkeypatch):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "ExportLockCo")
    monkeypatch.setenv("BAUPASS_ENV", "testing")
    monkeypatch.setattr(
        "backend.app.platform.security.contracts_lock._OTP_REQUEST_MIN_SECONDS",
        0,
    )

    setup = client.post(
        "/api/contracts/lock/request-otp",
        json={"company_id": company_id, "setup": True, "phone": "+491702222222", "email": "b@example.com"},
        headers=headers,
    )
    code = (setup.get_json() or {}).get("debugCode")
    client.post(
        "/api/contracts/lock/verify",
        json={
            "company_id": company_id,
            "setup": True,
            "phone": "+491702222222",
            "email": "b@example.com",
            "code": code,
        },
        headers=headers,
    )
    client.post("/api/contracts/lock", json={"company_id": company_id}, headers=headers)

    blocked = client.get(f"/api/workers/export.csv?company_id={company_id}", headers=headers)
    assert blocked.status_code == 403
    assert blocked.get_json().get("error") == "contracts_locked"
    assert blocked.get_json().get("stepUpRequired") is True


def test_owner_step_up_enforced_without_phone(client_and_db, monkeypatch):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "EnforceOwnerCo")
    monkeypatch.setenv("BAUPASS_OWNER_STEP_UP_ENFORCE", "1")
    monkeypatch.setenv("BAUPASS_ENV", "testing")

    status = client.get(f"/api/contracts/lock-status?company_id={company_id}", headers=headers)
    assert status.status_code == 200
    body = status.get_json()
    assert body["setupEnforced"] is True
    assert body["ownerSetupRequired"] is True
    assert body["lockRequired"] is True
    assert body["unlocked"] is False

    blocked = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    assert blocked.status_code == 403
    assert blocked.get_json().get("error") == "owner_setup_required"


def test_otp_debug_fallback_when_delivery_unavailable(client_and_db, monkeypatch):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "OtpDebugCo")
    monkeypatch.setenv("BAUPASS_ENV", "development")
    monkeypatch.setenv("BAUPASS_OWNER_OTP_ALLOW_DEBUG", "1")
    monkeypatch.setattr(
        "backend.app.platform.security.contracts_lock._OTP_REQUEST_MIN_SECONDS",
        0,
    )
    monkeypatch.setattr(
        "backend.app.platform.notifications.sms.sms_configured",
        lambda: False,
    )
    monkeypatch.setattr(
        "backend.server._send_otp_email_to_user",
        lambda *a, **k: False,
    )

    req = client.post(
        "/api/contracts/lock/request-otp",
        json={"company_id": company_id, "setup": True, "phone": "+491705555555", "email": "debug@example.com"},
        headers=headers,
    )
    assert req.status_code == 200, req.get_json()
    body = req.get_json() or {}
    assert body.get("debugCode")
    assert body.get("debugFallback") is True
    assert "debug" in (body.get("channels") or [])


def test_otp_request_rate_limit(client_and_db, monkeypatch):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "OtpRateCo")
    monkeypatch.setenv("BAUPASS_ENV", "testing")

    first = client.post(
        "/api/contracts/lock/request-otp",
        json={"company_id": company_id, "setup": True, "phone": "+491703333333", "email": "c@example.com"},
        headers=headers,
    )
    assert first.status_code == 200
    second = client.post(
        "/api/contracts/lock/request-otp",
        json={"company_id": company_id, "setup": True, "phone": "+491703333333", "email": "c@example.com"},
        headers=headers,
    )
    assert second.status_code == 429
    assert second.get_json().get("error") == "rate_limited"


def test_contracts_salary_redacted_when_locked(client_and_db, monkeypatch):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "SalaryRedactCo")
    monkeypatch.setenv("BAUPASS_ENV", "testing")
    monkeypatch.setattr(
        "backend.app.platform.security.contracts_lock._OTP_REQUEST_MIN_SECONDS",
        0,
    )

    setup = client.post(
        "/api/contracts/lock/request-otp",
        json={"company_id": company_id, "setup": True, "phone": "+491704444444", "email": "s@example.com"},
        headers=headers,
    )
    code = (setup.get_json() or {}).get("debugCode")
    client.post(
        "/api/contracts/lock/verify",
        json={
            "company_id": company_id,
            "setup": True,
            "phone": "+491704444444",
            "email": "s@example.com",
            "code": code,
        },
        headers=headers,
    )

    tpl = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    assert tpl.status_code == 200
    templates = (tpl.get_json() or {}).get("templates") or []
    assert templates
    template_id = templates[0]["id"]

    draft = client.post(
        "/api/contracts/draft",
        json={
            "company_id": company_id,
            "template_id": template_id,
            "form": {
                "employee_name": "Max Mustermann",
                "employee_gender": "male",
                "job_title": "Maurer",
                "start_date": "2026-08-01",
                "weekly_hours": "40",
                "salary_type": "monthly_fixed",
                "salary_gross_monthly": "3200",
                "currency": "EUR",
            },
        },
        headers=headers,
    )
    assert draft.status_code == 200, draft.get_json()
    contract_id = ((draft.get_json() or {}).get("contract") or {}).get("id")
    assert contract_id

    client.post("/api/contracts/lock", json={"company_id": company_id}, headers=headers)

    listed = client.get(f"/api/contracts?company_id={company_id}", headers=headers)
    assert listed.status_code == 200
    body = listed.get_json() or {}
    assert body.get("salaryRedacted") is True
    rows = body.get("contracts") or []
    assert rows
    assert "3200" not in str(rows[0].get("input_json") or "")
    assert rows[0].get("final_text") in ("", None)
    assert rows[0].get("draft_text") in ("", None)

    detail = client.get(f"/api/contracts/{contract_id}?company_id={company_id}", headers=headers)
    assert detail.status_code == 200
    d = detail.get_json() or {}
    assert d.get("salaryRedacted") is True
    assert d.get("bodyRedacted") is True
    assert not (d.get("final_text") or d.get("draft_text"))

    blocked_pdf = client.post(
        f"/api/contracts/{contract_id}/generate-pdf",
        json={"company_id": company_id},
        headers=headers,
    )
    assert blocked_pdf.status_code == 403
    assert blocked_pdf.get_json().get("error") == "contracts_locked"

    soft_worker = client.get(
        f"/api/workers/w-any/employment-contracts?company_id={company_id}",
        headers=headers,
    )
    assert soft_worker.status_code == 200
    assert soft_worker.get_json().get("salaryRedacted") is True
