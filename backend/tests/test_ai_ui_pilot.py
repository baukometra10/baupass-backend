"""UI pilot allowlist — safe navigation targets for the AI operator."""
from __future__ import annotations

from backend.app.platform.ai.ui_pilot import match_ui_pilot_target, try_ui_pilot_task


def test_ui_pilot_matches_core_tabs():
    assert match_ui_pilot_target("Öffne Tab Mitarbeiter") == "workers"
    assert match_ui_pilot_target("open tab operations") == "operations"
    assert match_ui_pilot_target("افتح تبويب العقود") == "contracts"


def test_ui_pilot_matches_hub_and_command_centers():
    assert match_ui_pilot_target("go to enterprise hub") == "hub"
    assert match_ui_pilot_target("ouvre ops command center") == "ops"
    assert match_ui_pilot_target("open AI command center") == "ai_center"


def test_ui_pilot_requires_navigate_intent():
    assert match_ui_pilot_target("who is on site today?") is None


def test_ui_pilot_task_returns_action():
    out = try_ui_pilot_task("click workers tab", lang="en")
    assert out and out.get("ok")
    assert out["actions"][0]["type"] == "ui_pilot"
    assert out["actions"][0]["target"] == "workers"
