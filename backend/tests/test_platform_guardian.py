"""Platform Guardian status and alerting."""
from __future__ import annotations

from backend.app.platform.guardian import notify, playbooks, runner, security


def test_merge_status_prefers_down():
    assert runner._merge_status("down", db_ok=True, workers_degraded=False) == "down"
    assert runner._merge_status("ok", db_ok=False, workers_degraded=False) == "degraded"
    assert runner._merge_status("ok", db_ok=True, workers_degraded=True) == "degraded"
    assert runner._merge_status("ok", db_ok=True, workers_degraded=False) == "ok"


def test_notify_skips_when_ok(monkeypatch):
    notify.reset_notify_state_for_tests()
    monkeypatch.setenv("BAUPASS_GUARDIAN_WEBHOOK_URL", "https://example.test/hook")
    result = notify.maybe_notify_guardian(
        {"status": "ok", "timestamp": "2026-06-01T12:00:00Z", "cloud": {"host": "test.local"}},
        previous_status="ok",
    )
    assert result.get("skipped") == "status_ok"


def test_notify_sends_on_degraded_transition(monkeypatch):
    notify.reset_notify_state_for_tests()
    monkeypatch.setenv("BAUPASS_GUARDIAN_WEBHOOK_URL", "https://example.test/hook")
    calls = []

    def _fake_send(url, text, *, title=""):
        calls.append({"url": url, "text": text, "title": title})
        return True, ""

    monkeypatch.setattr(
        "backend.app.platform.ai.notifications.send_webhook_notification",
        _fake_send,
    )
    result = notify.maybe_notify_guardian(
        {
            "status": "degraded",
            "ready": True,
            "timestamp": "2026-06-01T12:00:00Z",
            "cloud": {"host": "baupass.example"},
            "failedProbes": ["admin_v2"],
        },
        previous_status="ok",
    )
    assert result.get("sent") == 1
    assert calls
    assert "DEGRADED" in calls[0]["text"]


def test_playbook_cooldown(monkeypatch):
    playbooks.reset_playbook_state_for_tests()
    monkeypatch.setenv("BAUPASS_GUARDIAN_REMEDIATION_COOLDOWN_SECONDS", "3600")

    class _Db:
        def execute(self, *_args, **_kwargs):
            class _Cur:
                rowcount = 0

            return _Cur()

        def commit(self):
            return None

    first = playbooks.cleanup_expired_sessions(_Db())
    second = playbooks.cleanup_expired_sessions(_Db())
    assert first.get("ok") is True
    assert second.get("skipped") == "cooldown"


def test_security_detects_login_spike():
    class _Db:
        def execute(self, sql, params):
            class _Row:
                def __init__(self, c):
                    self._c = c

                def __getitem__(self, key):
                    return self._c

            if "15" in str(params[0]):
                return _Row(20)
            return _Row(10)

    report = security.scan_security(_Db())
    assert report["elevated"] is True
    assert report["failedLogins15m"] == 20
