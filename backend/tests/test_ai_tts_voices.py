"""TTS voice routing — ElevenLabs per-language defaults."""
from __future__ import annotations

from backend.app.platform.ai.tts import _ELEVENLABS_VOICES, _resolve_elevenlabs_config


def test_elevenlabs_fixed_voices_per_language():
    ar = _resolve_elevenlabs_config("ar")
    de = _resolve_elevenlabs_config("de")
    en = _resolve_elevenlabs_config("en")
    assert ar["voice_id"] == _ELEVENLABS_VOICES["ar"]
    assert de["voice_id"] == _ELEVENLABS_VOICES["de"]
    assert en["voice_id"] == _ELEVENLABS_VOICES["en"]
    assert ar["voice_name"] == "Ghizlane"
    assert de["voice_name"] == "Ramona"
    assert en["voice_name"] == "Vanessa"
