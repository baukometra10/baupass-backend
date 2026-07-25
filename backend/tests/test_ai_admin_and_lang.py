"""Admin AI model routing + language helpers + UI pilot."""
from __future__ import annotations

from backend.app.platform.ai.assistant import resolve_ai_model
from backend.app.platform.ai.langs import detect_lang_from_text, try_normalize_ui_lang
from backend.app.platform.ai.ui_pilot import try_ui_pilot_task


def test_admin_model_defaults_stronger(monkeypatch):
    monkeypatch.delenv("BAUPASS_AI_MODEL", raising=False)
    monkeypatch.delenv("BAUPASS_AI_MODEL_ADMIN", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_ADMIN", raising=False)
    model, _ = resolve_ai_model(role="company-admin")
    assert model == "gpt-4o"
    worker_model, _ = resolve_ai_model(role="worker")
    assert worker_model == "gpt-4o-mini"


def test_admin_model_env_override(monkeypatch):
    monkeypatch.setenv("BAUPASS_AI_MODEL_ADMIN", "gpt-4.1")
    model, _ = resolve_ai_model(role="superadmin")
    assert model == "gpt-4.1"


def test_lang_aliases_and_script_detect():
    assert try_normalize_ui_lang("german") == "de"
    assert try_normalize_ui_lang("turkish") == "tr"
    assert try_normalize_ui_lang("arz") == "ar"
    assert try_normalize_ui_lang("ar-SA") == "ar"
    assert detect_lang_from_text("من في الموقع اليوم؟") == "ar"
    assert detect_lang_from_text("مين موجود في الموقع النهاردة؟") == "ar"  # Egyptian dialect
    assert detect_lang_from_text("Wer ist heute vor Ort?") == "de"


def test_whisper_auto_not_truncated_to_au():
    from backend.app.platform.ai.whisper import _resolve_whisper_language

    auto, code = _resolve_whisper_language("auto")
    assert auto is True and code is None
    auto2, code2 = _resolve_whisper_language("ar")
    assert auto2 is False and code2 == "ar"
    auto3, code3 = _resolve_whisper_language("arz")
    assert auto3 is False and code3 == "ar"


def test_ui_pilot_click_workers():
    hit = try_ui_pilot_task("Bitte klicke den Mitarbeiter-Tab", lang="de")
    assert hit is not None
    assert hit["intent"] == "operator_ui_pilot"
    actions = hit.get("actions") or []
    assert actions and actions[0].get("type") == "ui_pilot"
    assert actions[0].get("tab") == "workers"
