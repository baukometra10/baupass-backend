"""Scale-ready gate path: keyed lookup, presence toggle, RQ notify enqueue."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from backend import server
from backend.app.middleware.rate_limiting import _detect_scope
from backend.app.platform.workforce.presence_state import (
    get_presence_open_direction,
    resolve_auto_direction,
    upsert_presence_after_access,
)
from backend.tests.test_outside_hours_employer_alert import _insert_gate_worker
from backend.tests.test_visitor_flow_api import _issue_turnstile_api_key


def test_rate_limit_detects_gates_plural_path():
    assert _detect_scope("/api/gates/tap", "POST") == "gate_api"
    assert _detect_scope("/api/gates/tap/batch", "POST") == "gate_api"
    assert _detect_scope("/api/gate/legacy", "POST") == "gate_api"


def test_turnstile_api_key_lookup_indexed(client_and_db):
    _client, db_path = client_and_db
    api_key = _issue_turnstile_api_key(db_path)
    lookup = server.turnstile_api_key_lookup(api_key)

    with server.app.app_context():
        db = server.get_db()
        try:
            db.execute(
                "UPDATE users SET api_key_lookup = ? WHERE role = 'turnstile'",
                (lookup,),
            )
            db.commit()
        except Exception:
            pytest.skip("api_key_lookup column not available")

        found = server.find_turnstile_by_api_key(db, api_key)
        assert found is not None
        assert str(found["role"]) == "turnstile"


def test_presence_toggle_roundtrip(tmp_path):
    db_path = tmp_path / "presence.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE worker_presence_state (
            worker_id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            open_direction TEXT NOT NULL DEFAULT '',
            last_checkin_at TEXT NOT NULL DEFAULT '',
            last_checkout_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE access_logs (
            id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );
        """
    )
    assert resolve_auto_direction(conn, "w1") == "check-in"
    upsert_presence_after_access(
        conn,
        worker_id="w1",
        company_id="c1",
        direction="check-in",
        timestamp_iso="2026-07-22T08:00:00Z",
    )
    assert get_presence_open_direction(conn, "w1") == "check-in"
    assert resolve_auto_direction(conn, "w1") == "check-out"
    upsert_presence_after_access(
        conn,
        worker_id="w1",
        company_id="c1",
        direction="check-out",
        timestamp_iso="2026-07-22T17:00:00Z",
    )
    assert get_presence_open_direction(conn, "w1") == ""
    assert resolve_auto_direction(conn, "w1") == "check-in"
    conn.close()


def test_schedule_outside_hours_uses_rq_when_available(monkeypatch):
    worker = {
        "id": "w1",
        "company_id": "c1",
        "first_name": "Ada",
        "last_name": "Lovelace",
    }
    attendance = {
        "ok": False,
        "reason": "outside_work_hours",
        "shiftStart": "08:00",
        "shiftEnd": "17:00",
        "message": "outside",
    }
    enqueue_mock = MagicMock()
    import backend.app.tasks as tasks_mod

    monkeypatch.setattr(tasks_mod, "enqueue", enqueue_mock)
    monkeypatch.setattr(tasks_mod, "_rq_queues", {"high": object()})
    server.schedule_outside_hours_checkin_notify(
        worker, attendance, channel="gate", gate="Nord"
    )
    assert enqueue_mock.called
    assert enqueue_mock.call_args.args[0] == "high"


def test_gate_checkout_allowed_outside_hours(client_and_db, monkeypatch):
    client, db_path = client_and_db
    monkeypatch.setattr(server, "worker_document_access_block", lambda *a, **k: None)
    monkeypatch.setattr(server, "worker_identity_access_block", lambda *a, **k: None)
    api_key = _issue_turnstile_api_key(db_path)
    _insert_gate_worker(
        db_path,
        worker_id="wrk-scale-out",
        card_id="NFC-SCALE-OUT",
        badge_id="BP-SCALE-OUT",
    )

    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            """
            INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp)
            VALUES (?, ?, 'check-in', 'Nordtor', 'seed', ?)
            """,
            ("log-scale-seed", "wrk-scale-out", datetime(2026, 6, 10, 8, 5).isoformat()),
        )
        try:
            db.execute(
                """
                INSERT OR REPLACE INTO worker_presence_state
                (worker_id, company_id, open_direction, last_checkin_at, last_checkout_at, updated_at)
                VALUES (?, 'cmp-default', 'check-in', ?, '', ?)
                """,
                (
                    "wrk-scale-out",
                    datetime(2026, 6, 10, 8, 5).isoformat(),
                    datetime(2026, 6, 10, 8, 5).isoformat(),
                ),
            )
        except sqlite3.OperationalError:
            pass
        db.commit()

    monkeypatch.setattr(
        "backend.app.platform.workforce.attendance_eligibility.worker_may_auto_attend_today",
        lambda *a, **k: {
            "ok": False,
            "reason": "outside_work_hours",
            "message": "blocked",
            "shiftStart": "08:00",
            "shiftEnd": "17:00",
        },
    )

    with patch.object(server, "schedule_outside_hours_checkin_notify") as notify_mock:
        resp_out = client.post(
            "/api/gates/tap",
            json={
                "physicalCardId": "NFC-SCALE-OUT",
                "direction": "check-out",
                "gate": "Nordtor",
                "eventId": "scale-checkout-1",
            },
            headers={"X-Gate-Key": api_key},
        )
        assert resp_out.status_code == 201, resp_out.get_json()
        notify_mock.assert_not_called()

        resp_in = client.post(
            "/api/gates/tap",
            json={
                "physicalCardId": "NFC-SCALE-OUT",
                "direction": "check-in",
                "gate": "Nordtor",
                "eventId": "scale-checkin-deny-1",
            },
            headers={"X-Gate-Key": api_key},
        )
        assert resp_in.status_code == 403
        body = resp_in.get_json() or {}
        assert body.get("error") == "outside_work_hours"
        assert notify_mock.call_count >= 1


def test_gate_batch_preserves_event_uid_idempotency(client_and_db, monkeypatch):
    client, db_path = client_and_db
    monkeypatch.setattr(server, "worker_document_access_block", lambda *a, **k: None)
    monkeypatch.setattr(server, "worker_identity_access_block", lambda *a, **k: None)
    monkeypatch.setattr(
        "backend.app.platform.workforce.attendance_eligibility.worker_may_auto_attend_today",
        lambda *a, **k: {"ok": True, "reason": "workday", "shiftStart": "08:00", "shiftEnd": "17:00"},
    )
    api_key = _issue_turnstile_api_key(db_path)
    _insert_gate_worker(
        db_path,
        worker_id="wrk-scale-batch",
        card_id="NFC-SCALE-BATCH",
        badge_id="BP-SCALE-BATCH",
    )

    event = {
        "physicalCardId": "NFC-SCALE-BATCH",
        "direction": "check-in",
        "gate": "Batch",
        "eventId": "batch-idem-1",
        "timestamp": "2026-07-22T09:00:00Z",
    }
    first = client.post(
        "/api/gates/tap/batch",
        json={"events": [event], "continueOnError": True},
        headers={"X-Gate-Key": api_key},
    )
    assert first.status_code == 200, first.get_json()
    first_body = first.get_json() or {}
    assert (first_body.get("results") or [{}])[0].get("status") == 201, first_body

    second = client.post(
        "/api/gates/tap/batch",
        json={"events": [event], "continueOnError": True},
        headers={"X-Gate-Key": api_key},
    )
    assert second.status_code == 200
    payload = second.get_json() or {}
    results = payload.get("results") or []
    assert results
    assert results[0].get("status") == 202
    assert results[0].get("duplicate") is True
