"""Worker document types, labels, and payroll helpers."""
from __future__ import annotations

ALLOWED_WORKER_DOC_TYPES = frozenset(
    {
        "mindestlohnnachweis",
        "personalausweis",
        "sozialversicherungsnachweis",
        "arbeitserlaubnis",
        "gesundheitszeugnis",
        "lohnabrechnung",
        "gehaltsabrechnung",
        "sonstiges",
    }
)

WORKER_PAYROLL_DOC_TYPES = frozenset({"lohnabrechnung", "gehaltsabrechnung"})

DOC_TYPE_LABELS: dict[str, dict[str, str]] = {
    "mindestlohnnachweis": {
        "de": "Mindestlohnnachweis",
        "en": "Minimum wage proof",
        "ar": "إثبات الحد الأدنى للأجر",
    },
    "personalausweis": {
        "de": "Personalausweis / Reisepass",
        "en": "ID / passport",
        "ar": "هوية / جواز سفر",
    },
    "sozialversicherungsnachweis": {
        "de": "Sozialversicherungsnachweis",
        "en": "Social security certificate",
        "ar": "شهادة الضمان الاجتماعي",
    },
    "arbeitserlaubnis": {
        "de": "Arbeitserlaubnis",
        "en": "Work permit",
        "ar": "تصريح عمل",
    },
    "gesundheitszeugnis": {
        "de": "Gesundheitszeugnis",
        "en": "Health certificate",
        "ar": "شهادة صحية",
    },
    "lohnabrechnung": {
        "de": "Lohnabrechnung",
        "en": "Payslip",
        "ar": "كشف الراتب",
    },
    "gehaltsabrechnung": {
        "de": "Gehaltsabrechnung",
        "en": "Salary statement",
        "ar": "كشف الراتب",
    },
    "sonstiges": {
        "de": "Sonstiges",
        "en": "Other",
        "ar": "أخرى",
    },
}


def normalize_doc_type(raw: str) -> str:
    value = (raw or "").strip().lower().replace(" ", "_")
    aliases = {
        "payroll": "lohnabrechnung",
        "payslip": "lohnabrechnung",
        "lohn": "lohnabrechnung",
        "gehalt": "gehaltsabrechnung",
        "salary": "gehaltsabrechnung",
    }
    return aliases.get(value, value)


def doc_type_label(doc_type: str, lang: str = "de") -> str:
    key = normalize_doc_type(doc_type)
    pack = DOC_TYPE_LABELS.get(key, {})
    lang = (lang or "de")[:2]
    return pack.get(lang) or pack.get("de") or key.replace("_", " ").title()


def doc_category(doc_type: str) -> str:
    return "payroll" if normalize_doc_type(doc_type) in WORKER_PAYROLL_DOC_TYPES else "compliance"


def is_payroll_doc_type(doc_type: str) -> bool:
    return normalize_doc_type(doc_type) in WORKER_PAYROLL_DOC_TYPES
