"""Account settings: password and username changes."""
from __future__ import annotations


def _superadmin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def test_superadmin_can_change_password(client_and_db):
    client, _ = client_and_db
    headers = _superadmin_headers(client)

    change = client.post(
        "/api/me/password",
        json={"currentPassword": "1234", "newPassword": "Testpass1"},
        headers=headers,
    )
    assert change.status_code == 200

    relogin = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "Testpass1", "loginScope": "server-admin"},
    )
    assert relogin.status_code == 200

    headers2 = {"Authorization": f"Bearer {relogin.get_json()['token']}"}
    revert = client.post(
        "/api/me/password",
        json={"currentPassword": "Testpass1", "newPassword": "1234"},
        headers=headers2,
    )
    assert revert.status_code == 200


def test_superadmin_can_change_username_and_display_name(client_and_db):
    client, db = client_and_db
    headers = _superadmin_headers(client)

    update = client.put(
        "/api/me/account",
        json={
            "currentPassword": "1234",
            "username": "superadmin_test",
            "name": "Systemleitung Test",
        },
        headers=headers,
    )
    assert update.status_code == 200
    payload = update.get_json()
    assert payload["user"]["username"] == "superadmin_test"
    assert payload["user"]["name"] == "Systemleitung Test"

    relogin = client.post(
        "/api/login",
        json={"username": "superadmin_test", "password": "1234", "loginScope": "server-admin"},
    )
    assert relogin.status_code == 200

    headers2 = {"Authorization": f"Bearer {relogin.get_json()['token']}"}
    revert = client.put(
        "/api/me/account",
        json={"currentPassword": "1234", "username": "superadmin", "name": "Systemleitung"},
        headers=headers2,
    )
    assert revert.status_code == 200


def test_account_update_rejects_wrong_password(client_and_db):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    resp = client.put(
        "/api/me/account",
        json={"currentPassword": "wrong", "username": "superadmin"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_current_password"
