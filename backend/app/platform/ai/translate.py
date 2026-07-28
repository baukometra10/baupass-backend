"""Chat / UI text translation via OpenAI-compatible chat completions."""
from __future__ import annotations

import os
from typing import Any

from .assistant import OpenAiApiError, _chat_completion, is_ai_configured
from .langs import LANG_NATIVE_NAMES, normalize_ui_lang, try_normalize_ui_lang

SUPPORTED = frozenset(LANG_NATIVE_NAMES.keys())

_PROMPTS = {
    "de": "Übersetze den folgenden Text ins Deutsche. Antworte nur mit der Übersetzung.",
    "en": "Translate the following text to English. Reply with the translation only.",
    "ar": "ترجم النص التالي إلى العربية فقط بدون شرح.",
    "tr": "Aşağıdaki metni Türkçeye çevir. Sadece çeviriyi yaz.",
    "fr": "Traduis le texte suivant en français. Réponds uniquement avec la traduction.",
    "es": "Traduce el siguiente texto al español. Responde solo con la traducción.",
    "it": "Traduci il seguente testo in italiano. Rispondi solo con la traduzione.",
    "pl": "Przetłumacz poniższy tekst na polski. Odpowiedz tylko tłumaczeniem.",
}


def chat_translate_enabled() -> bool:
    flag = (os.getenv("BAUPASS_CHAT_TRANSLATE") or "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return is_ai_configured()


def is_non_translatable_chat_text(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return True
    lowered = raw.lower()
    if lowered in {"encrypted", "🔒 verschlüsselte nachricht"}:
        return True
    if raw.startswith("@voice-call|") or raw.startswith("@location|"):
        return True
    if raw.startswith("{"):
        # E2E envelope JSON
        try:
            from backend.app.platform.security.e2e_envelope import is_e2e_envelope

            if is_e2e_envelope(raw):
                return True
        except Exception:
            if '"ciphertext"' in lowered or '"v":' in lowered[:40]:
                return True
    return False


def translate_text(
    text: str,
    *,
    target_lang: str,
    source_lang: str | None = None,
) -> dict[str, Any]:
    """
    Translate plaintext for chat display.
    Same source/target → skipped (no model call).
    """
    clean = str(text or "").strip()
    target = normalize_ui_lang(target_lang, default="en")
    source = try_normalize_ui_lang(source_lang)

    if not clean:
        return {
            "ok": False,
            "error": "empty_text",
            "targetLang": target,
            "sourceLang": source,
        }
    if is_non_translatable_chat_text(clean):
        return {
            "ok": False,
            "error": "not_translatable",
            "targetLang": target,
            "sourceLang": source,
            "text": clean,
        }
    if source and source == target:
        return {
            "ok": True,
            "skipped": True,
            "text": clean,
            "translation": clean,
            "targetLang": target,
            "sourceLang": source,
        }
    if not chat_translate_enabled():
        return {
            "ok": False,
            "error": "translate_unavailable",
            "hint": "OPENAI_API_KEY / Azure not configured or BAUPASS_CHAT_TRANSLATE=0",
            "targetLang": target,
            "sourceLang": source,
            "text": clean,
        }

    instruction = _PROMPTS.get(target) or _PROMPTS["en"]
    if source:
        native = LANG_NATIVE_NAMES.get(source, source)
        instruction = f"The source language is {native}. {instruction}"

    try:
        body = _chat_completion(
            [
                {"role": "system", "content": instruction},
                {"role": "user", "content": clean[:6000]},
            ]
        )
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        answer = str(message.get("content") or "").strip()
        if not answer:
            return {
                "ok": False,
                "error": "empty_translation",
                "targetLang": target,
                "sourceLang": source,
                "text": clean,
            }
        return {
            "ok": True,
            "skipped": False,
            "text": clean,
            "translation": answer,
            "targetLang": target,
            "sourceLang": source,
            "provider": "openai",
        }
    except OpenAiApiError as exc:
        return {
            "ok": False,
            "error": str(exc.code or "openai_error"),
            "hint": str(exc.hint or ""),
            "targetLang": target,
            "sourceLang": source,
            "text": clean,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": "translate_failed",
            "hint": str(exc)[:240],
            "targetLang": target,
            "sourceLang": source,
            "text": clean,
        }
