"""Worker document types, labels, and payroll helpers."""
from __future__ import annotations

ALLOWED_WORKER_DOC_TYPES = frozenset(
    {
        "mindestlohnnachweis",
        "personalausweis",
        "sozialversicherungsnachweis",
        "arbeitserlaubnis",
        "aufenthaltserlaubnis",
        "gesundheitszeugnis",
        "geburtsurkunde",
        "meldebescheinigung",
        "lohnabrechnung",
        "gehaltsabrechnung",
        "lohnsteuerbescheinigung",
        "verdienstabrechnung",
        "sonstiges",
    }
)

WORKER_PAYROLL_DOC_TYPES = frozenset(
    {
        "lohnabrechnung",
        "gehaltsabrechnung",
        "lohnsteuerbescheinigung",
        "verdienstabrechnung",
    }
)

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
    "aufenthaltserlaubnis": {
        "de": "Aufenthaltserlaubnis / Aufenthaltstitel",
        "en": "Residence permit",
        "ar": "تصريح إقامة",
    },
    "gesundheitszeugnis": {
        "de": "Gesundheitszeugnis",
        "en": "Health certificate",
        "ar": "شهادة صحية",
    },
    "geburtsurkunde": {
        "de": "Geburtsurkunde",
        "en": "Birth certificate",
        "ar": "شهادة ميلاد",
    },
    "meldebescheinigung": {
        "de": "Meldebescheinigung",
        "en": "Residence registration",
        "ar": "شهادة تسجيل السكن",
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
    "lohnsteuerbescheinigung": {
        "de": "Lohnsteuerbescheinigung",
        "en": "Income tax certificate",
        "ar": "شهادة ضريبة الدخل",
    },
    "verdienstabrechnung": {
        "de": "Verdienstabrechnung",
        "en": "Earnings statement",
        "ar": "كشف الأرباح",
    },
    "sonstiges": {
        "de": "Sonstiges",
        "en": "Other",
        "ar": "أخرى",
    },
    "einsatzplan": {
        "de": "Einsatzplan",
        "en": "Deployment plan",
        "ar": "خطة التوزيع",
    },
}


def normalize_doc_type(raw: str) -> str:
    value = (raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "payroll": "lohnabrechnung",
        "payslip": "lohnabrechnung",
        "lohn": "lohnabrechnung",
        "statement": "lohnabrechnung",
        "entgeltabrechnung": "lohnabrechnung",
        "gehalt": "gehaltsabrechnung",
        "salary": "gehaltsabrechnung",
        "id": "personalausweis",
        "passport": "personalausweis",
        "reisepass": "personalausweis",
        "ausweis": "personalausweis",
        "birth_certificate": "geburtsurkunde",
        "birth": "geburtsurkunde",
        "residence_permit": "aufenthaltserlaubnis",
        "aufenthaltstitel": "aufenthaltserlaubnis",
        "tax_certificate": "lohnsteuerbescheinigung",
        "income_tax_certificate": "lohnsteuerbescheinigung",
        "lohnsteuer": "lohnsteuerbescheinigung",
        "lohnsteuer_bescheinigung": "lohnsteuerbescheinigung",
        "earnings_statement": "verdienstabrechnung",
        "verdienstbescheinigung": "verdienstabrechnung",
        "verdienst_bescheinigung": "verdienstabrechnung",
        "verdienst_abrechnung": "verdienstabrechnung",
    }
    return aliases.get(value, value)


def resolve_payroll_doc_type(*sources: object, default: str = "lohnabrechnung") -> str:
    """Pick a canonical payroll doc type from delivery/statement dicts."""
    fallback = normalize_doc_type(default) if is_payroll_doc_type(default) else "lohnabrechnung"
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in ("documentType", "docType", "doc_type", "type"):
            raw = src.get(key)
            if raw is None or raw == "":
                continue
            norm = normalize_doc_type(str(raw))
            if norm in {"invoice", "invoices"}:
                continue
            if is_payroll_doc_type(norm):
                return norm
    return fallback


def doc_type_label(doc_type: str, lang: str = "de") -> str:
    key = normalize_doc_type(doc_type)
    pack = DOC_TYPE_LABELS.get(key, {})
    lang = (lang or "de")[:2]
    return pack.get(lang) or pack.get("de") or key.replace("_", " ").title()


def doc_category(doc_type: str) -> str:
    key = normalize_doc_type(doc_type)
    if key in WORKER_PAYROLL_DOC_TYPES:
        return "payroll"
    if key == "einsatzplan":
        return "schedule"
    return "compliance"


def is_payroll_doc_type(doc_type: str) -> bool:
    return normalize_doc_type(doc_type) in WORKER_PAYROLL_DOC_TYPES
