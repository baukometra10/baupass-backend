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


def test_company_create_explicit_usernames_and_login(client_and_db):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    response = client.post(
        "/api/companies",
        json={
            "name": "شركة تجريبية",
            "contact": "x",
            "adminUsername": "arabadmin01",
            "adminPassword": "Admin!23456",
            "officeUsername": "araboffice01",
            "officePassword": "Office!23456",
            "turnstilePassword": "Gate!234",
            "turnstileCount": 1,
        },
        headers=headers,
    )
    assert response.status_code in (200, 201), response.get_json()
    body = response.get_json() or {}
    admin = body.get("adminCredentials") or {}
    office = body.get("officeCredentials") or {}
    assert admin.get("username") == "arabadmin01"
    assert office.get("username") == "araboffice01"
    assert all(c.isascii() for c in admin["username"])
    assert all(c.isascii() for c in office["username"])

    admin_login = client.post(
        "/api/login",
        json={
            "username": "arabadmin01",
            "password": "Admin!23456",
            "loginScope": "company-admin",
        },
    )
    assert admin_login.status_code == 200, admin_login.get_json()
    assert ((admin_login.get_json() or {}).get("user") or {}).get("role") == "company-admin"

    office_via_company_scope = client.post(
        "/api/login",
        json={
            "username": "araboffice01",
            "password": "Office!23456",
            "loginScope": "company-admin",
        },
    )
    assert office_via_company_scope.status_code == 200, office_via_company_scope.get_json()
    assert ((office_via_company_scope.get_json() or {}).get("user") or {}).get("role") == "office"

    office_login = client.post(
        "/api/login",
        json={
            "username": "araboffice01",
            "password": "Office!23456",
            "loginScope": "office",
        },
    )
    assert office_login.status_code == 200, office_login.get_json()


def test_arabic_company_name_auto_usernames_are_ascii(client_and_db):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    response = client.post(
        "/api/companies",
        json={
            "name": "مؤسسة البناء",
            "contact": "x",
            "adminPassword": "Admin!23456",
            "officePassword": "Office!23456",
            "turnstilePassword": "Gate!234",
            "turnstileCount": 1,
        },
        headers=headers,
    )
    assert response.status_code in (200, 201), response.get_json()
    body = response.get_json() or {}
    admin = body.get("adminCredentials") or {}
    office = body.get("officeCredentials") or {}
    assert admin.get("username")
    assert office.get("username")
    assert all(c.isascii() for c in admin["username"])
    assert all(c.isascii() for c in office["username"])
    assert admin["username"] != office["username"]

    for cred, scope in ((admin, "company-admin"), (office, "office")):
        login = client.post(
            "/api/login",
            json={
                "username": cred["username"],
                "password": cred["password"],
                "loginScope": scope,
            },
        )
        assert login.status_code == 200, (cred, login.get_json())


def test_ensure_office_user_endpoint(client_and_db):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    created = client.post(
        "/api/companies",
        json={
            "name": "EnsureOfficeCo",
            "contact": "x",
            "adminUsername": "ensureadmin01",
            "adminPassword": "Admin!23456",
            "officeUsername": "ensureoffice01",
            "officePassword": "Office!23456",
            "turnstilePassword": "Gate!234",
            "turnstileCount": 1,
        },
        headers=headers,
    )
    assert created.status_code in (200, 201), created.get_json()
    company_id = str(((created.get_json() or {}).get("company") or {}).get("id") or "")
    assert company_id

    reset = client.post(
        f"/api/companies/{company_id}/ensure-office",
        json={"username": "ensureoffice01", "password": "OfficeNew!99"},
        headers=headers,
    )
    assert reset.status_code == 200, reset.get_json()
    cred = ((reset.get_json() or {}).get("officeCredentials") or {})
    assert cred.get("username") == "ensureoffice01"
    assert cred.get("password") == "OfficeNew!99"

    login = client.post(
        "/api/login",
        json={
            "username": "ensureoffice01",
            "password": "OfficeNew!99",
            "loginScope": "office",
        },
    )
    assert login.status_code == 200, login.get_json()
