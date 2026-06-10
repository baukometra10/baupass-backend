"""Spoken voice mode and TTS helpers."""
from __future__ import annotations

from backend.app.platform.ai.agents import agent_system_prompt
from backend.app.platform.ai.tts import synthesize_speech_bytes


def test_spoken_mode_adds_voice_rules():
    normal = agent_system_prompt("operations", "de", spoken=False)
    spoken = agent_system_prompt("operations", "de", spoken=True)
    assert "SPRACHMODUS" in spoken
    assert "SPRACHMODUS" not in normal


def test_tts_requires_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = synthesize_speech_bytes("Hallo Welt", lang="de")
    assert out["audio"] is None
    assert out["error"] == "openai_not_configured"
