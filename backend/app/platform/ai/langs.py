"""Shared UI / voice language codes for WorkPass AI (matches admin-v2 LANGS_8)."""
from __future__ import annotations

import re

SUPPORTED_UI_LANGS = frozenset({"de", "en", "ar", "tr", "fr", "es", "it", "pl"})

LANG_NATIVE_NAMES = {
    "de": "Deutsch",
    "en": "English",
    "ar": "العربية",
    "tr": "Türkçe",
    "fr": "français",
    "es": "español",
    "it": "italiano",
    "pl": "polski",
}

# Whisper / providers sometimes return English names, locale tags, or dialect codes.
_LANG_ALIASES = {
    "german": "de",
    "deutsch": "de",
    "english": "en",
    "arabic": "ar",
    "turkish": "tr",
    "french": "fr",
    "francais": "fr",
    "français": "fr",
    "spanish": "es",
    "espanol": "es",
    "español": "es",
    "italian": "it",
    "italiano": "it",
    "polish": "pl",
    "polski": "pl",
    # Common Arabic dialect / regional tags → system Arabic.
    "arz": "ar",  # Egyptian
    "apc": "ar",  # Levantine / North Levantine
    "ajp": "ar",  # South Levantine
    "afb": "ar",  # Gulf
    "arq": "ar",  # Algerian
    "ary": "ar",  # Moroccan
    "aeb": "ar",  # Tunisian
    "acm": "ar",  # Mesopotamian
    "acw": "ar",  # Hijazi
    "ars": "ar",  # Najdi
    "ayl": "ar",  # Libyan
    "shu": "ar",  # Chadian
    "arb": "ar",  # Standard Arabic
    "msa": "ar",
}


def try_normalize_ui_lang(lang: str | None) -> str | None:
    raw = str(lang or "").strip().lower().replace("_", "-")
    if not raw:
        return None
    if raw in _LANG_ALIASES:
        return _LANG_ALIASES[raw]
    # ar-SA / ar_EG / arz-EG
    if "-" in raw:
        left, right = raw.split("-", 1)
        if left in _LANG_ALIASES:
            return _LANG_ALIASES[left]
        if left in SUPPORTED_UI_LANGS:
            return left
        if right in _LANG_ALIASES:
            return _LANG_ALIASES[right]
    code = raw[:2]
    return code if code in SUPPORTED_UI_LANGS else None


def normalize_ui_lang(lang: str | None, default: str = "de") -> str:
    hit = try_normalize_ui_lang(lang)
    if hit:
        return hit
    fallback = try_normalize_ui_lang(default)
    return fallback or "de"


_ARABIC_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)


def detect_lang_from_text(text: str | None) -> str | None:
    """Best-effort script/keyword hint when Whisper does not return a language.

    Arabic (incl. dialects written in Arabic script) wins as soon as Arabic
    letters appear — MSA or dialect alike.
    """
    s = str(text or "").strip()
    if not s:
        return None
    arabic_chars = len(_ARABIC_RE.findall(s))
    if arabic_chars >= 1:
        return "ar"
    if re.search(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]", s):
        return "pl"
    if re.search(r"[ğüşıöçĞÜŞİÖÇ]", s):
        return "tr"
    if re.search(r"[àâçéèêëîïôùûüÿœæÀÂÇÉÈÊËÎÏÔÙÛÜŸŒÆ]", s) and re.search(
        r"\b(le|la|les|je|vous|bonjour|aujourd|qui|est)\b", s, re.I
    ):
        return "fr"
    if re.search(r"[áéíóúñü¿¡ÁÉÍÓÚÑÜ]", s) and re.search(
        r"\b(el|la|los|las|hola|gracias|quiero|quién)\b", s, re.I
    ):
        return "es"
    if re.search(r"[àèéìòùÀÈÉÌÒÙ]", s) and re.search(
        r"\b(il|lo|la|per|ciao|grazie|voglio|chi)\b", s, re.I
    ):
        return "it"
    if re.search(
        r"\b(ich|nicht|bitte|heute|mitarbeiter|urlaub|baustelle|wer|wie|was|und|oder|für)\b",
        s,
        re.I,
    ):
        return "de"
    if re.search(
        r"\b(the|please|today|workers?|leave|site|who|what|how|are|is|show|open|late|documents?)\b",
        s,
        re.I,
    ):
        return "en"
    return None


def reply_language_instruction(lang: str | None) -> str:
    code = normalize_ui_lang(lang)
    name = LANG_NATIVE_NAMES.get(code, code)
    if code == "ar":
        return (
            "Answer in Arabic (UI language code: ar). "
            "Understand Egyptian, Levantine, Gulf, Maghrebi, and other dialects; "
            "reply in clear simple Arabic (فصحى مبسطة) unless the user clearly prefers dialect phrasing. "
            "Only switch language if the user clearly writes in another supported language "
            f"({', '.join(sorted(SUPPORTED_UI_LANGS))})."
        )
    return (
        f"Answer in {name} (UI language code: {code}). "
        "Only switch language if the user clearly writes in another supported language "
        f"({', '.join(sorted(SUPPORTED_UI_LANGS))})."
    )


# Biases Whisper toward the 8 system languages (incl. dialectal Arabic).
WHISPER_MULTILINGUAL_PROMPT = (
    "WorkPass admin voice. Languages: Deutsch, English, العربية (فصحى وعامية مصرية شامية خليجية مغاربية), "
    "Türkçe, français, español, italiano, polski. "
    "Transcribe exactly in the spoken language/script. Arabic dialect → Arabic script."
)
