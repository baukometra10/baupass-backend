"""8-language helpers for deterministic AI operator tasks (LANGS_8)."""
from __future__ import annotations

from typing import Any

from .langs import SUPPORTED_UI_LANGS, normalize_ui_lang


def pick(
    lang: str | None,
    *,
    de: str,
    en: str,
    ar: str,
    tr: str = "",
    fr: str = "",
    es: str = "",
    it: str = "",
    pl: str = "",
) -> str:
    code = normalize_ui_lang(lang)
    table = {
        "de": de,
        "en": en,
        "ar": ar,
        "tr": tr or en,
        "fr": fr or en,
        "es": es or en,
        "it": it or en,
        "pl": pl or en,
    }
    return table.get(code) or en or de


def labels(
    *,
    de: str,
    en: str,
    ar: str,
    tr: str = "",
    fr: str = "",
    es: str = "",
    it: str = "",
    pl: str = "",
) -> dict[str, Any]:
    """Action label pack for FAB (labelDe… + labels{})."""
    pack = {
        "de": de,
        "en": en or de,
        "ar": ar or en or de,
        "tr": tr or en or de,
        "fr": fr or en or de,
        "es": es or en or de,
        "it": it or en or de,
        "pl": pl or en or de,
    }
    return {
        "labelDe": pack["de"],
        "labelEn": pack["en"],
        "labelAr": pack["ar"],
        "labelTr": pack["tr"],
        "labelFr": pack["fr"],
        "labelEs": pack["es"],
        "labelIt": pack["it"],
        "labelPl": pack["pl"],
        "labels": pack,
    }


# Fixed navigate blurbs (all 8 UI langs).
NAV_COPY: dict[str, dict[str, str]] = {
    "contracts": {
        "de": "Verträge / Contracts öffnen.",
        "en": "Opening contracts.",
        "ar": "فتح العقود.",
        "tr": "Sözleşmeler açılıyor.",
        "fr": "Ouverture des contrats.",
        "es": "Abriendo contratos.",
        "it": "Apertura contratti.",
        "pl": "Otwieram umowy.",
    },
    "docs": {
        "de": "Dokumenteneditor öffnen.",
        "en": "Opening documents editor.",
        "ar": "فتح محرر الوثائق.",
        "tr": "Belge editörü açılıyor.",
        "fr": "Ouverture de l'éditeur de documents.",
        "es": "Abriendo el editor de documentos.",
        "it": "Apertura editor documenti.",
        "pl": "Otwieram edytor dokumentów.",
    },
    "chat": {
        "de": "Firmen-Chat öffnen.",
        "en": "Opening company chat.",
        "ar": "فتح محادثة الشركة.",
        "tr": "Şirket sohbeti açılıyor.",
        "fr": "Ouverture du chat entreprise.",
        "es": "Abriendo el chat de la empresa.",
        "it": "Apertura chat aziendale.",
        "pl": "Otwieram czat firmowy.",
    },
    "workers": {
        "de": "Mitarbeiterliste öffnen.",
        "en": "Opening workers list.",
        "ar": "فتح قائمة الموظفين.",
        "tr": "Çalışan listesi açılıyor.",
        "fr": "Ouverture de la liste du personnel.",
        "es": "Abriendo la lista de trabajadores.",
        "it": "Apertura elenco lavoratori.",
        "pl": "Otwieram listę pracowników.",
    },
    "access": {
        "de": "Anwesenheit / Zutritt öffnen.",
        "en": "Opening attendance / access.",
        "ar": "فتح الحضور والدخول.",
        "tr": "Yoklama / giriş açılıyor.",
        "fr": "Ouverture présence / accès.",
        "es": "Abriendo asistencia / acceso.",
        "it": "Apertura presenza / accessi.",
        "pl": "Otwieram obecność / dostęp.",
    },
}

NAV_LABELS: dict[str, dict[str, str]] = {
    "contracts": {
        "de": "Verträge öffnen",
        "en": "Open contracts",
        "ar": "فتح العقود",
        "tr": "Sözleşmeleri aç",
        "fr": "Ouvrir les contrats",
        "es": "Abrir contratos",
        "it": "Apri contratti",
        "pl": "Otwórz umowy",
    },
    "docs": {
        "de": "Docs öffnen",
        "en": "Open docs",
        "ar": "فتح الوثائق",
        "tr": "Belgeleri aç",
        "fr": "Ouvrir docs",
        "es": "Abrir docs",
        "it": "Apri documenti",
        "pl": "Otwórz dokumenty",
    },
    "chat": {
        "de": "Chat öffnen",
        "en": "Open chat",
        "ar": "فتح المحادثة",
        "tr": "Sohbeti aç",
        "fr": "Ouvrir le chat",
        "es": "Abrir chat",
        "it": "Apri chat",
        "pl": "Otwórz czat",
    },
    "workers": {
        "de": "Mitarbeiter öffnen",
        "en": "Open workers",
        "ar": "فتح الموظفين",
        "tr": "Çalışanları aç",
        "fr": "Ouvrir le personnel",
        "es": "Abrir trabajadores",
        "it": "Apri lavoratori",
        "pl": "Otwórz pracowników",
    },
    "access": {
        "de": "Anwesenheit öffnen",
        "en": "Open attendance",
        "ar": "فتح الحضور",
        "tr": "Yoklamayı aç",
        "fr": "Ouvrir la présence",
        "es": "Abrir asistencia",
        "it": "Apri presenza",
        "pl": "Otwórz obecność",
    },
}


def nav_answer(lang: str | None, key: str) -> str:
    pack = NAV_COPY.get(key) or {}
    code = normalize_ui_lang(lang)
    return pack.get(code) or pack.get("en") or pack.get("de") or ""


def nav_labels(key: str) -> dict[str, Any]:
    pack = NAV_LABELS.get(key) or {}
    return labels(
        de=pack.get("de", key),
        en=pack.get("en", key),
        ar=pack.get("ar", ""),
        tr=pack.get("tr", ""),
        fr=pack.get("fr", ""),
        es=pack.get("es", ""),
        it=pack.get("it", ""),
        pl=pack.get("pl", ""),
    )


def assert_lang_pack_complete(pack: dict[str, str]) -> None:
    missing = SUPPORTED_UI_LANGS - set(pack)
    if missing:
        raise AssertionError(f"incomplete lang pack: {sorted(missing)}")
