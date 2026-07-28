"""Daily ops digest webhook (Slack/Teams) — soft summary only."""
from __future__ import annotations


def test_daily_ops_digest_skips_quiet_day(monkeypatch):
    from backend.app.platform.autopilot import runner as r

    class _Db:
        def execute(self, *_a, **_k):
            class _R:
                def fetchone(self):
                    return None

            return _R()

    monkeypatch.setattr(r, "_recent_autopilot_audit", lambda *_a, **_k: False)
    monkeypatch.setattr(
        "backend.app.platform.physical_operations.daily_brief.build_daily_ops_brief",
        lambda *_a, **_k: {
            "attendance": {"onSite": 1, "missingExpected": 0, "lateToday": 0},
            "security": {"totalOpen": 0, "openCameraEscalations": 0},
            "chat": {"totalOpen": 0},
            "hr": {"totalOpen": 0, "pendingLeave": 0, "expiringDocuments": 0, "inReviewDocuments": 0},
        },
    )
    out = r._send_daily_ops_digest(_Db(), "co-quiet")
    assert out.get("skipped") is True
    assert out.get("reason") == "quiet_day"


def test_daily_ops_digest_sends_when_signals(monkeypatch):
    from backend.app.platform.autopilot import runner as r

    class _Db:
        def execute(self, *_a, **_k):
            class _R:
                def fetchone(self):
                    return None

            return _R()

        def commit(self):
            return None

    sent = {"n": 0}

    monkeypatch.setattr(r, "_recent_autopilot_audit", lambda *_a, **_k: False)
    monkeypatch.setattr(r, "_log_autopilot", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "backend.app.platform.physical_operations.daily_brief.build_daily_ops_brief",
        lambda *_a, **_k: {
            "attendance": {"onSite": 2, "missingExpected": 1, "lateToday": 0},
            "security": {"totalOpen": 1, "openCameraEscalations": 1},
            "chat": {"totalOpen": 0},
            "hr": {"totalOpen": 1, "pendingLeave": 1, "expiringDocuments": 0, "inReviewDocuments": 0},
        },
    )
    monkeypatch.setattr(
        "backend.app.platform.inbox.slack_notify._webhook_urls",
        lambda: ["https://example.test/hook"],
    )
    monkeypatch.setattr(
        "backend.app.platform.ai.notifications.send_webhook_notification",
        lambda *_a, **_k: (True, ""),
    )

    def _alert(*_a, **_k):
        sent["n"] += 1

    monkeypatch.setattr("backend.server.create_system_alert", _alert)
    monkeypatch.setattr(
        "backend.app.platform.inbox.events.notify_inbox_changed",
        lambda *_a, **_k: None,
    )

    out = r._send_daily_ops_digest(_Db(), "co-busy")
    assert out.get("ok") is True
    assert int(out.get("sent") or 0) >= 1
    assert int(out.get("signals") or 0) >= 1
