"""Support assist spectator channel tests."""
from __future__ import annotations

from backend.app.platform.support_assist import service as assist_service


class _FakeDb:
    def execute(self, *_args, **_kwargs):
        return self

    def commit(self):
        return None


def test_start_session_and_poll_events(monkeypatch, tmp_path):
    assist_service._STORE_OVERRIDE = tmp_path / "support_assist.db"
    assist_service._sessions.clear()
    assist_service._schema_ready = False
    db = _FakeDb()
    started = assist_service.start_session(db, company_id="co-demo", actor_name="Support Team")
    assert started["watchToken"]
    assert started["companyId"] == "co-demo"

    polled = assist_service.poll_events(
        company_id="co-demo",
        watch_token=started["watchToken"],
        since_seq=0,
    )
    assert polled["active"] is True
    types = [evt["type"] for evt in polled["events"]]
    assert "session_start" in types
    assert "force_logout" not in types

    assist_service.append_pulse(
        company_id="co-demo",
        watch_token=started["watchToken"],
        event_type="mouse",
        payload={"x": 12, "y": 34},
    )
    polled2 = assist_service.poll_events(
        company_id="co-demo",
        watch_token=started["watchToken"],
        since_seq=polled["seq"],
    )
    assert polled2["lastMouse"]["x"] == 12
    assert polled2["lastMouse"]["y"] == 34

    assert assist_service.get_active_session("co-demo")["watchToken"] == started["watchToken"]

    assist_service.end_session(company_id="co-demo", watch_token=started["watchToken"])
    assert assist_service.get_active_session("co-demo") is None
    ended = assist_service.poll_events(
        company_id="co-demo",
        watch_token=started["watchToken"],
        since_seq=polled2["seq"],
    )
    assert ended["active"] is False
    assert ended["ended"] is True
    assert any(evt["type"] == "session_end" for evt in ended["events"])


def test_get_watch_session_validates_token(tmp_path):
    assist_service._STORE_OVERRIDE = tmp_path / "support_assist.db"
    assist_service._sessions.clear()
    assist_service._schema_ready = False
    db = _FakeDb()
    started = assist_service.start_session(db, company_id="co-demo", actor_name="Support Team")
    row = assist_service.get_watch_session("co-demo", started["watchToken"])
    assert row is not None
    assert row["companyId"] == "co-demo"
    assert row["actorName"] == "Support Team"
    assert assist_service.get_watch_session("co-demo", "wrong-token") is None
