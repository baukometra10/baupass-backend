"""Outside-hours check-in: employer notify + gate enforcement."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from backend import server
from backend.app.platform.notifications.company_mitteilung import (
    OUTSIDE_HOURS_NOTIFY_REASONS,
    maybe_notify_outside_hours_attempt,
    notify_company_outside_hours_checkin_attempt,
)
from backend.tests.test_visitor_flow_api import _issue_turnstile_api_key


def test_outside_hours_notify_reasons_cover_time_windows():
    assert "outside_work_hours" in OUTSIDE_HOURS_NOTIFY_REASONS
    assert "outside_shift_window" in OUTSIDE_HOURS_NOTIFY_REASONS
    assert "not_scheduled_today" in OUTSIDE_HOURS_NOTIFY_REASONS
    assert "not_a_workday" in OUTSIDE_HOURS_NOTIFY_REASONS
    assert "on_approved_leave" not in OUTSIDE_HOURS_NOTIFY_REASONS
    assert "visitor_not_eligible" not in OUTSIDE_HOURS_NOTIFY_REASONS


def test_outside_hours_alert_copy_localizes():
    from backend.app.platform.notifications.company_mitteilung import build_outside_hours_alert_copy

    de = build_outside_hours_alert_copy(
        worker_name="Max Muster",
        reason="outside_work_hours",
        channel="gate",
        gate="Nordtor",
        shift_start="08:00",
        shift_end="17:00",
        lang="de",
    )
    en = build_outside_hours_alert_copy(
        worker_name="Max Muster",
        reason="outside_work_hours",
        channel="gate",
        gate="Nordtor",
        shift_start="08:00",
        shift_end="17:00",
        lang="en",
    )
    ar = build_outside_hours_alert_copy(
        worker_name="Max Muster",
        reason="outside_work_hours",
        channel="gps",
        lang="ar",
    )
    assert "außerhalb der Arbeitszeit" in de["title"]
    assert "Sign-in outside working hours" in en["title"]
    assert "ساعات العمل" in ar["title"]
    assert "Max Muster" in en["body"]
    assert "Gate/Reader" in en["body"]
    assert "08:00" in de["body"] and "17:00" in de["body"]


def test_notify_creates_alert_and_dedups(client_and_db, monkeypatch):
    _client, db_path = client_and_db
    monkeypatch.setattr(server, "_send_via_any_api", lambda *a, **k: (True, None, "test"))
    inbox = MagicMock()
    monkeypatch.setattr(
        "backend.app.platform.inbox.events.notify_inbox_changed",
        inbox,
    )
    monkeypatch.setattr(
        "backend.app.platform.push.admin_delivery.deliver_admin_push",
        MagicMock(return_value={"ok": True, "sent": 0}),
    )

    with server.app.app_context():
        db = server.get_db()
        db.execute(
            "UPDATE companies SET billing_email = ?, work_start_time = ?, work_end_time = ? WHERE id = ?",
            ("boss@example.com", "08:00", "17:00", "cmp-default"),
        )
        db.commit()

        first = notify_company_outside_hours_checkin_attempt(
            db,
            company_id="cmp-default",
            worker_id="wrk-1",
            worker_name="Max Muster",
            reason="outside_work_hours",
            channel="gps",
            shift_start="08:00",
            shift_end="17:00",
        )
        assert first["ok"] is True
        assert first.get("deduped") is False
        assert first.get("alertId")

        second = notify_company_outside_hours_checkin_attempt(
            db,
            company_id="cmp-default",
            worker_id="wrk-1",
            worker_name="Max Muster",
            reason="outside_work_hours",
            channel="gps",
            shift_start="08:00",
            shift_end="17:00",
        )
        assert second["ok"] is True
        assert second.get("deduped") is True
        assert second.get("alertId") is None
        assert second.get("emailsSent") == 0

        alerts = db.execute(
            "SELECT code, severity FROM system_alerts WHERE code = ?",
            ("outside_hours_checkin_attempt",),
        ).fetchall()
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "warning"

    assert inbox.call_count == 1


def test_maybe_notify_skips_non_trigger_reasons(client_and_db):
    _client, _db_path = client_and_db
    worker = {
        "id": "wrk-x",
        "company_id": "cmp-default",
        "first_name": "A",
        "last_name": "B",
    }
    with server.app.app_context():
        db = server.get_db()
        result = maybe_notify_outside_hours_attempt(
            db,
            worker,
            {"ok": False, "reason": "on_approved_leave", "message": "Urlaub"},
            channel="gps",
        )
        assert result is None
        result_ok = maybe_notify_outside_hours_attempt(
            db,
            worker,
            {"ok": True, "reason": "workday"},
            channel="gps",
        )
        assert result_ok is None


def _insert_gate_worker(db_path, *, worker_id, card_id, badge_id):
    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, visitor_company, visit_purpose,
                host_name, visit_end_at, status, photo_data, badge_id, badge_pin_hash,
                physical_card_id, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                worker_id,
                "cmp-default",
                None,
                "Late",
                "Worker",
                f"SV-{worker_id}",
                "worker",
                "Monteur",
                "Nordtor",
                "2030-01-01",
                "",
                "",
                "",
                "",
                "aktiv",
                "data:image/png;base64,AAA",
                badge_id,
                "",
                card_id,
                None,
            ),
        )
        db.execute(
            "UPDATE companies SET work_start_time = ?, work_end_time = ? WHERE id = ?",
            ("08:00", "17:00", "cmp-default"),
        )
        db.commit()


def test_gate_checkin_outside_work_hours_denied_and_notifies(client_and_db, monkeypatch):
    client, db_path = client_and_db
    monkeypatch.setattr(server, "worker_document_access_block", lambda *a, **k: None)
    monkeypatch.setattr(server, "worker_identity_access_block", lambda *a, **k: None)
    notify_calls = []

    def _capture_schedule(worker, attendance, *, channel, gate=""):
        notify_calls.append(
            {
                "workerId": str(worker["id"]),
                "reason": str((attendance or {}).get("reason") or ""),
                "channel": channel,
                "gate": gate,
            }
        )

    monkeypatch.setattr(server, "schedule_outside_hours_checkin_notify", _capture_schedule)
    api_key = _issue_turnstile_api_key(db_path)
    _insert_gate_worker(
        db_path,
        worker_id="wrk-outside-in",
        card_id="NFC-OUTSIDE-IN",
        badge_id="BP-OUTSIDE-IN",
    )

    fixed_now = datetime(2026, 6, 10, 22, 30, 0)  # Wednesday after work hours
    from backend.app.platform.workforce import attendance_eligibility as elig

    original = elig.worker_may_auto_attend_today

    def _eligibility(db, worker, **kwargs):
        kwargs.setdefault("now", fixed_now)
        kwargs.setdefault("target_date", fixed_now.date())
        return original(db, worker, **kwargs)

    monkeypatch.setattr(elig, "worker_may_auto_attend_today", _eligibility)

    response = client.post(
        "/api/gates/tap",
        json={
            "physicalCardId": "NFC-OUTSIDE-IN",
            "direction": "check-in",
            "gate": "Nordtor",
        },
        headers={"X-Gate-Key": api_key},
    )
    assert response.status_code == 403
    payload = response.get_json() or {}
    assert payload.get("error") == "outside_work_hours"
    assert len(notify_calls) == 1
    assert notify_calls[0]["reason"] == "outside_work_hours"
    assert notify_calls[0]["channel"] == "gate"
    assert notify_calls[0]["gate"] == "Nordtor"

    with closing(sqlite3.connect(db_path)) as db:
        logs = db.execute(
            "SELECT id FROM access_logs WHERE worker_id = ?",
            ("wrk-outside-in",),
        ).fetchall()
        assert len(logs) == 0


def test_gate_checkout_outside_work_hours_still_allowed(client_and_db, monkeypatch):
    client, db_path = client_and_db
    monkeypatch.setattr(server, "worker_document_access_block", lambda *a, **k: None)
    monkeypatch.setattr(server, "worker_identity_access_block", lambda *a, **k: None)
    api_key = _issue_turnstile_api_key(db_path)
    _insert_gate_worker(
        db_path,
        worker_id="wrk-outside-out",
        card_id="NFC-OUTSIDE-OUT",
        badge_id="BP-OUTSIDE-OUT",
    )

    # Seed an open check-in so checkout is meaningful; checkout must not hit eligibility.
    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            """
            INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp)
            VALUES (?, ?, 'check-in', 'Nordtor', 'seed', ?)
            """,
            ("log-seed-out", "wrk-outside-out", datetime(2026, 6, 10, 8, 5).isoformat()),
        )
        db.commit()

    fixed_now = datetime(2026, 6, 10, 22, 45, 0)
    from backend.app.platform.workforce import attendance_eligibility as elig

    original = elig.worker_may_auto_attend_today

    def _eligibility(db, worker, **kwargs):
        kwargs.setdefault("now", fixed_now)
        kwargs.setdefault("target_date", fixed_now.date())
        return original(db, worker, **kwargs)

    monkeypatch.setattr(elig, "worker_may_auto_attend_today", _eligibility)

    with patch.object(server, "schedule_outside_hours_checkin_notify") as notify_mock:
        response = client.post(
            "/api/gates/tap",
            json={
                "physicalCardId": "NFC-OUTSIDE-OUT",
                "direction": "check-out",
                "gate": "Nordtor",
            },
            headers={"X-Gate-Key": api_key},
        )
        assert response.status_code == 201
        notify_mock.assert_not_called()

    with closing(sqlite3.connect(db_path)) as db:
        checkout = db.execute(
            """
            SELECT direction FROM access_logs
            WHERE worker_id = ? AND direction = 'check-out'
            """,
            ("wrk-outside-out",),
        ).fetchone()
        assert checkout is not None
