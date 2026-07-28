"""Push deeplink tags for missed calls + morning brief."""
from __future__ import annotations

from backend.app.platform.push.deeplinks import push_data_payload


def test_morning_brief_deeplink_goes_home():
    data = push_data_payload(tag="morning-brief", worker_id="w1")
    assert data["tag"] == "morning-brief"
    assert "home" in data["route"] or data["route"].endswith("/app/home") or "baupass://app/home" in data["route"]


def test_voice_call_missed_deeplink_opens_chat():
    data = push_data_payload(
        tag="voice-call-missed",
        worker_id="w1",
        extra={"callId": "vc-9"},
    )
    assert "chat" in data["route"]
    assert "missed=1" in data["route"]
    assert "vc-9" in data["route"]
    assert data.get("autoDial") is None
