"""Deployment day decline/swap rules: check-in lock + cutoff before shift start."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.platform.workforce.deployment_responses import (
    decline_cutoff_hours,
    evaluate_decline_allowed,
    evaluate_swap_allowed,
    swap_cutoff_hours,
)


class _FakeDb:
    def __init__(self, rows=None):
        self._rows = rows or []

    def execute(self, sql, params=()):
        class _Cur:
            def __init__(self, rows):
                self._rows = rows

            def fetchone(self):
                return self._rows[0] if self._rows else None

        # check-in query
        if "access_logs" in sql:
            day = params[1] if len(params) > 1 else ""
            hits = [r for r in self._rows if r.get("day") == day]
            return _Cur(hits)
        return _Cur([])


def test_decline_blocked_after_checkin():
    day = date.today() + timedelta(days=2)
    db = _FakeDb(rows=[{"id": "al-1", "day": day.isoformat()}])
    ok, reason, _meta = evaluate_decline_allowed(
        db,
        worker_id="w1",
        work_date=day,
        shift_start="09:00",
    )
    assert ok is False
    assert reason == "checked_in"


def test_decline_cutoff_blocks_near_start(monkeypatch):
    monkeypatch.setenv("BAUPASS_DEPLOYMENT_DECLINE_CUTOFF_HOURS", "2")
    monkeypatch.setenv("BAUPASS_BUSINESS_TZ", "Europe/Berlin")
    tz = ZoneInfo("Europe/Berlin")
    # Freeze "now" to 08:00 on work day; shift at 09:00 → within 2h cutoff
    fixed = datetime(2026, 8, 20, 8, 0, tzinfo=tz)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed.replace(tzinfo=None)
            return fixed.astimezone(tz)

    import backend.app.platform.workforce.deployment_responses as mod

    monkeypatch.setattr(mod, "datetime", _FixedDateTime)
    db = _FakeDb()
    ok, reason, meta = evaluate_decline_allowed(
        db,
        worker_id="w1",
        work_date=date(2026, 8, 20),
        shift_start="09:00",
    )
    assert ok is False
    assert reason == "cutoff"
    assert float(meta["cutoffHours"]) == 2.0


def test_decline_allowed_well_before_start(monkeypatch):
    monkeypatch.setenv("BAUPASS_DEPLOYMENT_DECLINE_CUTOFF_HOURS", "2")
    monkeypatch.setenv("BAUPASS_BUSINESS_TZ", "Europe/Berlin")
    tz = ZoneInfo("Europe/Berlin")
    fixed = datetime(2026, 8, 19, 10, 0, tzinfo=tz)  # day before

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed.replace(tzinfo=None)
            return fixed.astimezone(tz)

    import backend.app.platform.workforce.deployment_responses as mod

    monkeypatch.setattr(mod, "datetime", _FixedDateTime)
    db = _FakeDb()
    ok, reason, _meta = evaluate_decline_allowed(
        db,
        worker_id="w1",
        work_date=date(2026, 8, 20),
        shift_start="09:00",
    )
    assert ok is True
    assert reason == ""


def test_decline_cutoff_hours_default():
    assert decline_cutoff_hours() >= 0.25


def test_swap_cutoff_default_one_hour(monkeypatch):
    monkeypatch.delenv("BAUPASS_DEPLOYMENT_SWAP_CUTOFF_HOURS", raising=False)
    assert abs(swap_cutoff_hours() - 1.0) < 0.01


def test_swap_cutoff_blocks_within_one_hour(monkeypatch):
    monkeypatch.setenv("BAUPASS_DEPLOYMENT_SWAP_CUTOFF_HOURS", "1")
    monkeypatch.setenv("BAUPASS_BUSINESS_TZ", "Europe/Berlin")
    tz = ZoneInfo("Europe/Berlin")
    # 08:30 with shift 09:00 → within 1h
    fixed = datetime(2026, 8, 20, 8, 30, tzinfo=tz)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed.replace(tzinfo=None)
            return fixed.astimezone(tz)

    import backend.app.platform.workforce.deployment_responses as mod

    monkeypatch.setattr(mod, "datetime", _FixedDateTime)
    db = _FakeDb()
    ok, reason, meta = evaluate_swap_allowed(
        db,
        worker_id="w1",
        work_date=date(2026, 8, 20),
        shift_start="09:00",
    )
    assert ok is False
    assert reason == "cutoff"
    assert float(meta["cutoffHours"]) == 1.0


def test_swap_allowed_more_than_one_hour_before(monkeypatch):
    monkeypatch.setenv("BAUPASS_DEPLOYMENT_SWAP_CUTOFF_HOURS", "1")
    monkeypatch.setenv("BAUPASS_BUSINESS_TZ", "Europe/Berlin")
    tz = ZoneInfo("Europe/Berlin")
    fixed = datetime(2026, 8, 20, 7, 0, tzinfo=tz)  # 2h before

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed.replace(tzinfo=None)
            return fixed.astimezone(tz)

    import backend.app.platform.workforce.deployment_responses as mod

    monkeypatch.setattr(mod, "datetime", _FixedDateTime)
    db = _FakeDb()
    ok, reason, _meta = evaluate_swap_allowed(
        db,
        worker_id="w1",
        work_date=date(2026, 8, 20),
        shift_start="09:00",
    )
    assert ok is True
    assert reason == ""


def test_swap_blocked_when_already_swapped_out():
    db = _FakeDb()
    ok, reason, _meta = evaluate_swap_allowed(
        db,
        worker_id="w1",
        work_date=date.today() + timedelta(days=3),
        shift_start="09:00",
        swap_status="out",
    )
    assert ok is False
    assert reason == "swapped_out"
