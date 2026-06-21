from __future__ import annotations

import json

import pytest


def test_validate_hourly_skips_gross():
    from backend.app.domains.contracts.validation import validate_contract_form

    template = {"contract_type": "employment", "required_fields_json": json.dumps(["salary_gross_monthly"])}
    missing = validate_contract_form(
        {
            "employee_name": "Max Mustermann",
            "employee_gender": "male",
            "employee_address": "Berlin",
            "job_title": "Clerk",
            "start_date": "2026-01-01",
            "work_location": "Office",
            "salary_type": "hourly",
            "hourly_rate": "18.50",
        },
        template=template,
        lang="de",
    )
    assert "Bruttogehalt" not in missing
    assert missing == []


def test_submit_signature_requires_consent(client_and_db):
    client, _ = client_and_db
    headers_resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert headers_resp.status_code == 200
    headers = {"Authorization": f"Bearer {headers_resp.get_json()['token']}"}

    company = client.post(
        "/api/companies",
        json={
            "name": "SignCo",
            "contact": "x",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 0,
        },
        headers=headers,
    )
    company_id = (company.get_json().get("company") or {}).get("id") or company.get_json().get("id")

    templates = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    template_list = templates.get_json()["templates"]
    template_id = next(
        (t["id"] for t in template_list if t.get("template_key") == "permanent_full_time"),
        template_list[0]["id"],
    )

    draft = client.post(
        "/api/contracts/draft",
        json={
            "company_id": company_id,
            "template_id": template_id,
            "title": "Testvertrag",
            "language": "de",
            "form": {
                "employee_name": "Anna Test",
                "employee_gender": "female",
                "employee_address": "Berlin",
                "job_title": "Kraft",
                "start_date": "2026-07-01",
                "work_location": "Lager",
                "weekly_hours": "40",
                "vacation_days": "28",
                "probation_months": "6",
                "salary_type": "hourly",
                "hourly_rate": "15",
            },
        },
        headers=headers,
    )
    contract_id = draft.get_json()["contract"]["id"]

    client.put(
        f"/api/contracts/{contract_id}",
        json={
            "company_id": company_id,
            "final_text": "Vertragstext mit Stundenlohn 15 EUR.",
            "form": {
                "employee_name": "Anna Test",
                "employee_gender": "female",
                "employee_address": "Berlin",
                "job_title": "Kraft",
                "start_date": "2026-07-01",
                "work_location": "Lager",
                "weekly_hours": "40",
                "vacation_days": "28",
                "probation_months": "6",
                "salary_type": "hourly",
                "hourly_rate": "15",
            },
        },
        headers=headers,
    )

    link = client.post(
        f"/api/contracts/{contract_id}/sign-link",
        json={
            "company_id": company_id,
            "role": "employee",
            "form": {
                "employee_name": "Anna Test",
                "employee_gender": "female",
                "employee_address": "Berlin",
                "job_title": "Kraft",
                "start_date": "2026-07-01",
                "work_location": "Lager",
                "weekly_hours": "40",
                "vacation_days": "28",
                "probation_months": "6",
                "salary_type": "hourly",
                "hourly_rate": "15",
            },
        },
        headers=headers,
    )
    assert link.status_code == 200
    token = link.get_json()["token"]

    blocked = client.post(
        f"/api/public/contracts/sign/{token}",
        json={"signer_name": "Anna Test", "signature_data": "", "sign_place": "Berlin", "consent_accepted": False},
    )
    assert blocked.status_code == 400
    assert blocked.get_json().get("error") == "consent_required"

    ok = client.post(
        f"/api/public/contracts/sign/{token}",
        json={
            "signer_name": "Anna Test",
            "signature_data": "",
            "sign_place": "Berlin",
            "consent_accepted": True,
            "sign_latitude": 52.52,
            "sign_longitude": 13.405,
        },
    )
    assert ok.status_code == 200
    assert ok.get_json().get("ok") is True

    events = client.get(f"/api/contracts/{contract_id}/events?company_id={company_id}", headers=headers)
    assert events.status_code == 200
    types = [row.get("event_type") for row in events.get_json().get("events") or []]
    assert "contract.signed" in types

    client.delete(f"/api/contracts/{contract_id}?company_id={company_id}", headers=headers)


def test_integrations_status(client_and_db):
    client, _ = client_and_db
    headers_resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    headers = {"Authorization": f"Bearer {headers_resp.get_json()['token']}"}
    company = client.post(
        "/api/companies",
        json={
            "name": "IntCo",
            "contact": "x",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 0,
        },
        headers=headers,
    )
    company_id = (company.get_json().get("company") or {}).get("id") or company.get_json().get("id")
    resp = client.get(f"/api/contracts/integrations-status?company_id={company_id}", headers=headers)
    assert resp.status_code == 200
    body = resp.get_json()
    assert "emailConfigured" in body
    assert "smsConfigured" in body
