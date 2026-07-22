"""Company-scoped event log + superadmin audit summary."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing

from backend import server
from backend.app.platform.audit.service import audit_summary, build_audit_query, list_audit_events
from backend.app.platform.plan_entitlements import min_plan_for_capability


def _superadmin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def _company_admin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "firma", "password": "1234", "loginScope": "company-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def _seed_audit(db_path, rows):
    with closing(sqlite3.connect(db_path)) as db:
        for row in rows:
            db.execute(
                """
                INSERT INTO audit_logs (
                    id, event_type, actor_user_id, actor_role, company_id,
                    target_type, target_id, message, created_at,
                    details_json, reason, actor_name, ip_address
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
        db.commit()


def test_audit_capability_on_lowest_plan():
    assert min_plan_for_capability("audit") == "tageskarte"


def test_build_audit_query_strict_company_isolation():
    where, params = build_audit_query(
        role="company-admin",
        user_company_id="cmp-a",
        company_id="cmp-b",
        strict_company=True,
    )
    assert "company_id = ?" in where
    assert params == ["cmp-a"]


def test_company_admin_cannot_see_other_company(client_and_db):
    client, db_path = client_and_db
    _seed_audit(
        db_path,
        [
            (
                "aud-own",
                "contract.updated",
                "usr-company",
                "company-admin",
                "cmp-default",
                "employment_contract",
                "ctr-1",
                "Own company change",
                "2099-01-02T10:00:00Z",
                json.dumps({"field": "salary"}),
                "salary bump",
                "Firmen-Admin",
                "127.0.0.1",
            ),
            (
                "aud-other",
                "contract.updated",
                "usr-x",
                "company-admin",
                "cmp-other",
                "employment_contract",
                "ctr-2",
                "Other company secret",
                "2099-01-02T11:00:00Z",
                "{}",
                "",
                "Other",
                "10.0.0.1",
            ),
        ],
    )
    headers = _company_admin_headers(client)
    res = client.get("/api/audit-events?limit=50", headers=headers)
    assert res.status_code == 200
    body = res.get_json()
    ids = {e["id"] for e in body["events"]}
    assert "aud-own" in ids
    assert "aud-other" not in ids
    # Even if they try to request another company
    res2 = client.get("/api/audit-events?companyId=cmp-other", headers=headers)
    assert res2.status_code == 200
    ids2 = {e["id"] for e in res2.get_json()["events"]}
    assert "aud-other" not in ids2


def test_log_audit_stores_rich_fields(client_and_db):
    client, db_path = client_and_db
    with server.app.app_context():
        server.log_audit(
            "settings.updated",
            "Work times changed",
            target_type="company",
            target_id="cmp-default",
            company_id="cmp-default",
            actor={"id": "usr-company", "role": "company-admin", "name": "Firmen-Admin"},
            details={"before": {"start": "08:00"}, "after": {"start": "07:30"}},
            reason="Frühschicht",
        )
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT * FROM audit_logs WHERE event_type = ? ORDER BY created_at DESC LIMIT 1",
            ("settings.updated",),
        ).fetchone()
        assert row is not None
        assert row["reason"] == "Frühschicht"
        assert row["actor_name"] == "Firmen-Admin"
        details = json.loads(row["details_json"] or "{}")
        assert details["after"]["start"] == "07:30"


def test_superadmin_summary_and_filter(client_and_db):
    client, db_path = client_and_db
    _seed_audit(
        db_path,
        [
            (
                "aud-a1",
                "worker.updated",
                "u1",
                "company-admin",
                "cmp-default",
                "worker",
                "w1",
                "Worker A",
                "2099-06-01T12:00:00Z",
                "{}",
                "",
                "Admin A",
                "",
            ),
            (
                "aud-b1",
                "worker.updated",
                "u2",
                "company-admin",
                "cmp-other",
                "worker",
                "w2",
                "Worker B",
                "2099-06-01T13:00:00Z",
                "{}",
                "",
                "Admin B",
                "",
            ),
        ],
    )

    headers = _superadmin_headers(client)
    summary = client.get("/api/audit-events/summary?days=36500", headers=headers)
    assert summary.status_code == 200
    data = summary.get_json()
    assert data["total"] >= 2
    assert any(x["eventType"] == "worker.updated" for x in data["byEventType"])

    filtered = client.get("/api/audit-events?companyId=cmp-other&limit=20", headers=headers)
    assert filtered.status_code == 200
    ids = {e["id"] for e in filtered.get_json()["events"]}
    assert "aud-b1" in ids
    assert "aud-a1" not in ids


def test_list_audit_events_unit(client_and_db):
    _client, db_path = client_and_db
    _seed_audit(
        db_path,
        [
            (
                "aud-u1",
                "contract.signed",
                "usr-company",
                "company-admin",
                "cmp-default",
                "employment_contract",
                "c1",
                "Signed",
                "2099-07-01T08:00:00Z",
                json.dumps({"role": "employer"}),
                "Abschluss",
                "Firmen-Admin",
                "1.2.3.4",
            ),
        ],
    )
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        result = list_audit_events(
            db,
            role="company-admin",
            user_company_id="cmp-default",
            event_type="contract.",
            query_text="Signed",
        )
        assert result["total"] == 1
        ev = result["events"][0]
        assert ev["details"]["role"] == "employer"
        assert ev["reason"] == "Abschluss"
        assert ev["actorName"] == "Firmen-Admin"
        assert ev["ipAddress"] == "1.2.3.4"

        summ = audit_summary(
            db,
            role="company-admin",
            user_company_id="cmp-default",
            days=36500,
        )
        assert summ["total"] >= 1


def test_audit_routes_registered(client_and_db):
    client, _db = client_and_db
    rules = [rule.rule for rule in server.app.url_map.iter_rules()]
    for path in ("/api/audit-logs", "/api/audit-events", "/api/audit-events/summary", "/api/audit-logs/export.csv"):
        assert path in rules
    # unauthenticated
    assert client.get("/api/audit-events").status_code in (401, 403)
