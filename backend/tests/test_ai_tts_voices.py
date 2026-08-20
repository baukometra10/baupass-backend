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
    monkeypatch.delenv("SUPPIX_TTS_PROVIDER", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
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
    monkeypatch.delenv("SUPPIX_TTS_PROVIDER", raising=False)
    status = tts_config_status()
    assert status["provider"] == "openai"
    assert status["configured"] is True
    assert status["voices"]["ar"]["name"] == "Ghizlane"


def test_tts_auto_prefers_openai_when_both_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test")
    monkeypatch.delenv("BAUPASS_TTS_PROVIDER", raising=False)
    monkeypatch.delenv("SUPPIX_TTS_PROVIDER", raising=False)
    assert _resolve_tts_provider() == "openai"


def test_tts_auto_uses_elevenlabs_without_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test")
    monkeypatch.delenv("BAUPASS_TTS_PROVIDER", raising=False)
    monkeypatch.delenv("SUPPIX_TTS_PROVIDER", raising=False)
    assert _resolve_tts_provider() == "elevenlabs"


def test_tts_suppix_provider_alias(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test")
    monkeypatch.setenv("SUPPIX_TTS_PROVIDER", "openai")
    monkeypatch.delenv("BAUPASS_TTS_PROVIDER", raising=False)
    assert _resolve_tts_provider() == "openai"


def test_elevenlabs_voice_env_all_eight_langs(monkeypatch):
    from backend.app.platform.ai.tts import _resolve_elevenlabs_config
    from backend.app.platform.ai.langs import SUPPORTED_UI_LANGS

    for code in SUPPORTED_UI_LANGS:
        monkeypatch.setenv(f"BAUPASS_ELEVENLABS_VOICE_{code.upper()}", f"voice-{code}")
    for code in SUPPORTED_UI_LANGS:
        cfg = _resolve_elevenlabs_config(code)
        assert cfg["voice_id"] == f"voice-{code}"
        assert cfg["voice_name"]


def test_openai_personas_cover_all_ui_langs():
    from backend.app.platform.ai.langs import SUPPORTED_UI_LANGS

    for code in SUPPORTED_UI_LANGS:
        assert code in _VOICE_PERSONAS
        cfg = _resolve_openai_config(code)
        assert cfg["voice_name"]
        assert cfg["voice"]
