"""Deployment day decline rules: check-in lock + cutoff before shift start."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.app.platform.workforce.deployment_responses import (
    decline_cutoff_hours,
    evaluate_decline_allowed,
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
