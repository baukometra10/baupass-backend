"""Autopilot settings merge defaults."""
from backend.app.platform.autopilot.settings import DEFAULTS, merge_settings


def test_merge_settings_empty():
    out = merge_settings(None)
    assert out["autoAckInfoAlerts"] is True
    assert out["autoNotifyDocExpiryDays"] == 14
    assert out["autoSuggestPendingLeave"] is True
    assert out["autoSuggestDocsReview"] is True
    assert out["autoSendDeploymentPlans"] is False


def test_merge_settings_patch():
    raw = '{"autoNotifyDocExpiry": false, "unknown": true, "autoSuggestPendingLeave": false}'
    out = merge_settings(raw)
    assert out["autoNotifyDocExpiry"] is False
    assert out["autoSuggestPendingLeave"] is False
    assert "unknown" not in out
    assert out["autoAckInfoAlerts"] == DEFAULTS["autoAckInfoAlerts"]
    assert out["autoSuggestDocsReview"] == DEFAULTS["autoSuggestDocsReview"]
