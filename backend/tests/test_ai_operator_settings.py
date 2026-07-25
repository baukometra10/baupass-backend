"""Company AI Operator FAB enable/disable settings."""
from __future__ import annotations

from backend.app.platform.ai.operator_settings import get_settings, save_settings


class _FakeDb:
    def __init__(self):
        self.rows = {}
        self._ensured = False

    def execute(self, sql, params=None):
        sql_l = " ".join(str(sql).lower().split())
        if sql_l.startswith("create table"):
            self._ensured = True
            return self
        if "select" in sql_l and "company_ai_operator_settings" in sql_l:
            cid = params[0]
            raw = self.rows.get(cid)

            class Row(dict):
                def __getitem__(self, key):
                    return dict.get(self, key)

            if not raw:
                return _Result(None)
            return _Result(Row({"settings_json": raw, "updated_at": "t"}))
        if "insert" in sql_l:
            cid, payload, *_rest = params
            self.rows[cid] = payload
            return self
        return self

    def commit(self):
        return None

    def fetchone(self):
        return None


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


def test_operator_settings_default_enabled():
    db = _FakeDb()
    s = get_settings(db, "cmp-1")
    assert s["enabled"] is True


def test_operator_settings_disable_and_enable():
    db = _FakeDb()
    s = save_settings(db, "cmp-1", {"enabled": False}, actor="admin")
    assert s["enabled"] is False
    s2 = save_settings(db, "cmp-1", {"enabled": True}, actor="admin")
    assert s2["enabled"] is True


def test_operator_settings_voice_and_welcome_flags():
    db = _FakeDb()
    s = save_settings(
        db,
        "cmp-1",
        {"enabled": True, "voiceEnabled": False, "welcomeEnabled": False},
        actor="admin",
    )
    assert s["enabled"] is True
    assert s["voiceEnabled"] is False
    assert s["welcomeEnabled"] is False
    s2 = save_settings(db, "cmp-1", {"voiceEnabled": True}, actor="admin")
    assert s2["voiceEnabled"] is True
    assert s2["welcomeEnabled"] is False
