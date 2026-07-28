"""Unit tests for chat translate helper (no live OpenAI)."""
from __future__ import annotations

from backend.app.platform.ai.translate import is_non_translatable_chat_text, translate_text


def test_same_lang_skips_without_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    out = translate_text("Hallo Team", target_lang="de", source_lang="de")
    assert out["ok"] is True
    assert out["skipped"] is True
    assert out["translation"] == "Hallo Team"


def test_empty_text_rejected():
    out = translate_text("   ", target_lang="en", source_lang="de")
    assert out["ok"] is False
    assert out["error"] == "empty_text"


def test_system_markers_not_translatable():
    assert is_non_translatable_chat_text("@location|lat=1|lng=2")
    assert is_non_translatable_chat_text("@voice-call|status=ended")
    out = translate_text("@location|lat=1|lng=2", target_lang="en", source_lang="de")
    assert out["ok"] is False
    assert out["error"] == "not_translatable"


def test_missing_provider_returns_unavailable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("BAUPASS_CHAT_TRANSLATE", "1")
    out = translate_text("مرحبا", target_lang="en", source_lang="ar")
    assert out["ok"] is False
    assert out["error"] == "translate_unavailable"
