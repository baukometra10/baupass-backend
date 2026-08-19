"""Worker document types, labels, and payroll helpers."""
from __future__ import annotations

import re

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
        "jahresabrechnung",
        "vordienstbescheinigung",
        "lohn_unterlage",
        "sonstiges",
    }
)

WORKER_PAYROLL_DOC_TYPES = frozenset(
    {
        "lohnabrechnung",
        "gehaltsabrechnung",
        "lohnsteuerbescheinigung",
        "verdienstabrechnung",
        "jahresabrechnung",
        "vordienstbescheinigung",
        "lohn_unterlage",
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
    "jahresabrechnung": {
        "de": "Jahresabrechnung",
        "en": "Annual statement",
        "ar": "كشف حساب سنوي",
    },
    "vordienstbescheinigung": {
        "de": "Vordienstbescheinigung",
        "en": "Prior employment certificate",
        "ar": "شهادة خدمة سابقة",
    },
    "lohn_unterlage": {
        "de": "Lohn-Unterlage",
        "en": "Payroll document",
        "ar": "مستند رواتب",
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
        "monatsabrechnung": "lohnabrechnung",
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
        "annual_statement": "jahresabrechnung",
        "jahres_abrechnung": "jahresabrechnung",
        "year_end": "jahresabrechnung",
        "prior_employment": "vordienstbescheinigung",
        "vordienst": "vordienstbescheinigung",
        "vordienst_bescheinigung": "vordienstbescheinigung",
        "payroll_document": "lohn_unterlage",
        "document": "lohn_unterlage",
        "unterlage": "lohn_unterlage",
    }
    return aliases.get(value, value)


def infer_payroll_doc_type_from_title(title: str) -> str | None:
    """Map free-text Lohn titles (DE/EN/AR) to a payroll doc type."""
    raw = str(title or "").strip()
    if not raw:
        return None
    # Exact slug-like titles
    as_type = normalize_doc_type(raw)
    if is_payroll_doc_type(as_type):
        return as_type
    text = raw.lower()
    text_compact = re.sub(r"[\s_\-./]+", "", text)
    rules: list[tuple[str, tuple[str, ...]]] = [
        (
            "vordienstbescheinigung",
            ("vordienst", "prior employment", "previous employment", "خدمة سابقة", "خدمة سابقه"),
        ),
        (
            "jahresabrechnung",
            ("jahresabrechnung", "jahres", "annual", "year-end", "yearend", "سنوي", "كشف حساب سنوي"),
        ),
        (
            "lohnsteuerbescheinigung",
            ("lohnsteuer", "tax certificate", "income tax", "ضريبة الدخل", "ضريبة"),
        ),
        (
            "verdienstabrechnung",
            ("verdienstabrechnung", "verdienstbescheinigung", "earnings", "كشف أرباح", "كشف الارباح"),
        ),
        (
            "gehaltsabrechnung",
            ("gehaltsabrechnung", "gehalt", "salary statement"),
        ),
        (
            "lohnabrechnung",
            (
                "lohnabrechnung",
                "entgeltabrechnung",
                "monatsabrechnung",
                "payslip",
                "payroll",
                "شهري",
                "كشف الراتب",
                "كشف راتب",
            ),
        ),
    ]
    for doc_type, needles in rules:
        for needle in needles:
            n = needle.lower()
            if n in text or n.replace(" ", "") in text_compact:
                return doc_type
    return None


def resolve_document_title(*sources: object) -> str:
    """Return the Lohn-provided title unchanged (trimmed)."""
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in ("title", "subject", "headline", "label", "documentTitle", "name"):
            raw = src.get(key)
            if raw is None or raw == "":
                continue
            title = str(raw).strip()
            if title:
                return title[:240]
    return ""


def resolve_payroll_doc_type(*sources: object, default: str = "lohnabrechnung") -> str:
    """Pick a canonical payroll doc type from delivery/statement dicts and titles."""
    fallback = normalize_doc_type(default) if is_payroll_doc_type(default) else "lohnabrechnung"
    generic = {"lohn_unterlage", "document", "payroll_document", "unterlage"}
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in ("documentType", "docType", "doc_type", "type"):
            raw = src.get(key)
            if raw is None or raw == "":
                continue
            raw_l = str(raw).strip().lower()
            if raw_l in {"invoice", "invoices"} or normalize_doc_type(raw_l) in {"invoice", "invoices"}:
                continue
            # Generic "document" must not win over an explicit title like Vordienstbescheinigung.
            if raw_l in generic or normalize_doc_type(raw_l) == "lohn_unterlage":
                continue
            norm = normalize_doc_type(str(raw))
            if is_payroll_doc_type(norm):
                return norm
            inferred = infer_payroll_doc_type_from_title(str(raw))
            if inferred:
                return inferred
        title = resolve_document_title(src)
        if title:
            inferred = infer_payroll_doc_type_from_title(title)
            if inferred:
                return inferred
    for src in sources:
        if isinstance(src, dict) and resolve_document_title(src):
            return "lohn_unterlage"
    return fallback


def display_document_label(*sources: object, doc_type: str = "", lang: str = "de") -> str:
    """Prefer the exact Lohn title; fall back to typed label."""
    title = resolve_document_title(*sources)
    if title:
        return title
    return doc_type_label(doc_type or "lohnabrechnung", lang=lang)


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
