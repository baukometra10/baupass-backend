"""Tests for superadmin IP whitelist policy."""
from __future__ import annotations

import sqlite3

import pytest

from backend.app.platform.security.admin_ip_access import (
    check_superadmin_ip_access,
    clear_admin_ip_policy,
    ip_allowed,
    parse_ip_whitelist,
    should_enforce_admin_ip,
)
from backend.app.platform.security.client_ip import resolve_client_ip
from backend import server


def test_parse_ip_whitelist_accepts_cidr_and_commas():
    assert parse_ip_whitelist("203.0.113.10, 203.0.113.0/24") == ["203.0.113.10", "203.0.113.0/24"]


def test_ip_allowed_matches_host_and_network():
    whitelist = ["203.0.113.10", "203.0.113.0/24"]
    assert ip_allowed("203.0.113.10", whitelist) is True
    assert ip_allowed("203.0.113.55", whitelist) is True
    assert ip_allowed("198.51.100.1", whitelist) is False


def test_whitelist_not_enforced_without_opt_in(client_and_db, monkeypatch):
    client, db_path = client_and_db
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE settings SET admin_ip_whitelist = '198.51.100.1' WHERE id = 1")
    conn.commit()
    conn.close()

    monkeypatch.delenv("BAUPASS_ENFORCE_ADMIN_IP_WHITELIST", raising=False)
    monkeypatch.delenv("BAUPASS_ADMIN_IP_WHITELIST_DISABLED", raising=False)

    login = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
        headers={"X-Forwarded-For": "203.0.113.99"},
    )
    assert login.status_code == 200
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}", "X-Forwarded-For": "203.0.113.99"}

    companies = client.get("/api/companies", headers=headers)
    assert companies.status_code == 200


def test_whitelist_enforced_when_opted_in(client_and_db, monkeypatch):
    client, db_path = client_and_db
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE settings SET admin_ip_whitelist = '198.51.100.1', enforce_admin_ip_whitelist = 1 WHERE id = 1"
    )
    conn.commit()
    conn.close()

    monkeypatch.delenv("BAUPASS_ADMIN_IP_WHITELIST_DISABLED", raising=False)

    login = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
        headers={"X-Forwarded-For": "203.0.113.99"},
    )
    assert login.status_code == 200
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}", "X-Forwarded-For": "203.0.113.99"}

    companies = client.get("/api/companies", headers=headers)
    assert companies.status_code == 403
    payload = companies.get_json()
    assert payload["error"] == "admin_ip_not_allowed"
    assert payload["clientIp"] == "203.0.113.99"


def test_whitelist_disabled_by_env(client_and_db, monkeypatch):
    client, db_path = client_and_db
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE settings SET admin_ip_whitelist = '198.51.100.1', enforce_admin_ip_whitelist = 1 WHERE id = 1"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("BAUPASS_ADMIN_IP_WHITELIST_DISABLED", "1")

    login = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
        headers={"X-Forwarded-For": "203.0.113.99"},
    )
    assert login.status_code == 200
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}", "X-Forwarded-For": "203.0.113.99"}

    companies = client.get("/api/companies", headers=headers)
    assert companies.status_code == 200


def test_recovery_clears_ip_whitelist(client_and_db, monkeypatch):
    client, db_path = client_and_db
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE settings SET admin_ip_whitelist = '198.51.100.1', enforce_admin_ip_whitelist = 1 WHERE id = 1"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("BAUPASS_RECOVERY_SECRET", "recovery-test-secret")

    res = client.post(
        "/api/system/clear-admin-ip-whitelist",
        json={"recoverySecret": "recovery-test-secret"},
    )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT admin_ip_whitelist, enforce_admin_ip_whitelist FROM settings WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row[0] == ""
    assert int(row[1]) == 0


def test_resolve_client_ip_prefers_cf_header(client_and_db):
    client, _ = client_and_db
    with client.application.test_request_context(
        "/",
        headers={
            "CF-Connecting-IP": "203.0.113.44",
            "X-Forwarded-For": "10.0.0.1, 203.0.113.44",
        },
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
    ):
        assert resolve_client_ip() == "203.0.113.44"
