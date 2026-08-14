"""Office operator RBAC: ops allowed, payroll/contracts blocked."""
from __future__ import annotations


def _superadmin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def test_company_create_returns_office_credentials(client_and_db):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    response = client.post(
        "/api/companies",
        json={
            "name": "OfficeRbacCo",
            "contact": "x",
            "adminPassword": "Admin!234",
            "officePassword": "Office!234",
            "turnstilePassword": "Gate!234",
            "turnstileCount": 1,
        },
        headers=headers,
    )
    assert response.status_code in (200, 201), response.get_json()
    body = response.get_json() or {}
    office = body.get("officeCredentials") or {}
    assert office.get("username")
    assert office.get("password") == "Office!234"
    admin = body.get("adminCredentials") or {}
    assert admin.get("username")
    assert admin.get("username") != office.get("username")

    login = client.post(
        "/api/login",
        json={
            "username": office["username"],
            "password": office["password"],
            "loginScope": "office",
        },
    )
    assert login.status_code == 200, login.get_json()
    user = (login.get_json() or {}).get("user") or {}
    assert user.get("role") == "office"
    office_headers = {"Authorization": f"Bearer {(login.get_json() or {}).get('token')}"}

    company_id = str((body.get("company") or {}).get("id") or "")
    workers = client.get(f"/api/workers?company_id={company_id}", headers=office_headers)
    assert workers.status_code == 200, workers.get_json()

    contracts = client.get(f"/api/contracts/templates?company_id={company_id}", headers=office_headers)
    assert contracts.status_code == 403

    payroll = client.get(
        f"/api/payroll/accounting/company-settings?company_id={company_id}",
        headers=office_headers,
    )
    assert payroll.status_code == 403

    audit = client.get(f"/api/audit-events?limit=5&companyId={company_id}", headers=office_headers)
    assert audit.status_code == 403
