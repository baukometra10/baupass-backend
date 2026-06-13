"""TTS voice routing — OpenAI personas Ghizlane / Ramona / Vanessa."""
from __future__ import annotations

from backend.app.platform.ai.tts import (
    _VOICE_PERSONAS,
    _resolve_openai_config,
    _resolve_tts_provider,
    tts_config_status,
)


def test_openai_persona_voices_per_language(monkeypatch):
    monkeypatch.delenv("BAUPASS_TTS_PROVIDER", raising=False)
    monkeypatch.delenv("BAUPASS_TTS_VOICE_AR", raising=False)
    monkeypatch.delenv("BAUPASS_TTS_VOICE_DE", raising=False)
    monkeypatch.delenv("BAUPASS_TTS_VOICE_EN", raising=False)
    assert _resolve_tts_provider() == "openai"
    ar = _resolve_openai_config("ar")
    de = _resolve_openai_config("de")
    en = _resolve_openai_config("en")
    assert ar["voice_name"] == "Ghizlane"
    assert de["voice_name"] == "Ramona"
    assert en["voice_name"] == "Vanessa"
    assert ar["voice"] == _VOICE_PERSONAS["ar"]["openai_voice"]
    assert de["voice"] == _VOICE_PERSONAS["de"]["openai_voice"]
    assert en["voice"] == _VOICE_PERSONAS["en"]["openai_voice"]


def test_tts_status_defaults_to_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("BAUPASS_TTS_PROVIDER", raising=False)
    status = tts_config_status()
    assert status["provider"] == "openai"
    assert status["configured"] is True
    assert status["voices"]["ar"]["name"] == "Ghizlane"
