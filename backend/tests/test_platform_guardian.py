"""Platform Guardian status and alerting."""
from __future__ import annotations

from backend.app.platform.guardian import notify, runner


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
