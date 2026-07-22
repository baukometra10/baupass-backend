"""High-assurance worker document verification.

Validates uploads before they become compliance evidence:
- magic-byte MIME sniffing (do not trust client Content-Type)
- size / format constraints for document uploads
- OCR / PDF text heuristics that the content matches the claimed type
  (ID/passport, birth certificate, government certificates, etc.)

Encrypted E2E attachments skip content OCR but still require a sane size.
"""
from __future__ import annotations

import os
import re
from typing import Any

# Worker document uploads only — never audio/video/word-as-ID by default.
WORKER_DOC_ALLOWED_MIMES = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)

# Types that must look like official / identity paperwork.
HIGH_ASSURANCE_DOC_TYPES = frozenset(
    {
        "personalausweis",
        "sozialversicherungsnachweis",
        "arbeitserlaubnis",
        "gesundheitszeugnis",
        "mindestlohnnachweis",
        "geburtsurkunde",
        "meldebescheinigung",
        "aufenthaltserlaubnis",
    }
)

_MIN_BYTES = 800
_MAX_IMAGE_BYTES_DEFAULT = 12 * 1024 * 1024
_MIN_IMAGE_SIDE = 120

_MRZ_HINT = re.compile(
    r"(P<[A-Z]{3}|ID[A-Z]{3}|[A-Z0-9<]{20,}<<)|"
    r"\b(document\s*no|doc\.?\s*no|pass\s*no|ausweisnummer)\b",
    re.IGNORECASE,
)

_TYPE_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "personalausweis": (
        re.compile(
            r"\b(personalausweis|reisepass|passport|identity\s*card|id[\s-]?card|"
            r"bundesrepublik|deutscher?\s+ausweis|carte\s+d['’]?identit|"
            r"هوية|جواز\s*سفر|national\s+id)\b",
            re.IGNORECASE,
        ),
        _MRZ_HINT,
        re.compile(r"\b(geburtsdatum|date\s+of\s+birth|nationalit|geschlecht|sex)\b", re.IGNORECASE),
    ),
    "geburtsurkunde": (
        re.compile(
            r"\b(geburtsurkunde|birth\s*certificate|standesamt|geburtsort|"
            r"شهادة\s*ميلاد|acte\s+de\s+naissance)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\b(geboren|born|vater|mutter|father|mother|eltern)\b", re.IGNORECASE),
    ),
    "meldebescheinigung": (
        re.compile(
            r"\b(meldebescheinigung|meldebestätigung|wohnungsgeber|"
            r"einwohnermeldeamt|anmeldebescheinigung)\b",
            re.IGNORECASE,
        ),
    ),
    "sozialversicherungsnachweis": (
        re.compile(
            r"\b(sozialversicherung|sozialversicherungsnummer|sv[\s-]?nr|"
            r"rentenversicherung|krankenversicherung|mitgliedsbescheinigung)\b",
            re.IGNORECASE,
        ),
    ),
    "arbeitserlaubnis": (
        re.compile(
            r"\b(arbeitserlaubnis|aufenthaltstitel|aufenthaltserlaubnis|"
            r"work\s*permit|residence\s*permit|beschäftigungserlaubnis)\b",
            re.IGNORECASE,
        ),
    ),
    "aufenthaltserlaubnis": (
        re.compile(
            r"\b(aufenthaltstitel|aufenthaltserlaubnis|residence\s*permit|"
            r"visa|schengen)\b",
            re.IGNORECASE,
        ),
    ),
    "gesundheitszeugnis": (
        re.compile(
            r"\b(gesundheitszeugnis|gesundheitsbescheinigung|ärztliche?\s+bescheinigung|"
            r"health\s*certificate|infektionsschutz|bescheinigung\s+nach)\b",
            re.IGNORECASE,
        ),
    ),
    "mindestlohnnachweis": (
        re.compile(
            r"\b(mindestlohn|mindestlohnnachweis|minimum[\s-]?wage|"
            r"lohnnachweis|entgeltnachweis)\b",
            re.IGNORECASE,
        ),
    ),
    "lohnabrechnung": (
        re.compile(
            r"\b(lohnabrechnung|gehaltsabrechnung|payslip|entgelt|"
            r"brutto|netto|datev)\b",
            re.IGNORECASE,
        ),
    ),
    "gehaltsabrechnung": (
        re.compile(
            r"\b(gehaltsabrechnung|lohnabrechnung|payslip|salary|"
            r"brutto|netto)\b",
            re.IGNORECASE,
        ),
    ),
}

# Generic “looks like junk / not a document” signals
_JUNK_HINTS = re.compile(
    r"\b(lorem\s+ipsum|hello\s+world|test\s+file|sample\s+pdf|"
    r"this\s+is\s+a\s+test|untitled\s+document)\b",
    re.IGNORECASE,
)


def verification_enabled() -> bool:
    raw = (os.getenv("BAUPASS_DOC_VERIFY") or "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def verification_strict() -> bool:
    """When True, high-assurance docs are rejected if content cannot be verified."""
    raw = (os.getenv("BAUPASS_DOC_VERIFY_STRICT") or "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def sniff_mime(raw: bytes, filename: str = "") -> str | None:
    """Return a trusted MIME from file signatures (not client headers)."""
    if not raw:
        return None
    head = raw[:16]
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    # Reject HTML / script disguised with a document extension
    sample = raw[:2048].lstrip().lower()
    if sample.startswith(b"<!doctype html") or sample.startswith(b"<html") or sample.startswith(b"<script"):
        return None
    ext = (filename or "").rsplit(".", 1)
    suffix = f".{ext[-1].lower()}" if len(ext) == 2 else ""
    # Extension alone is never enough for high assurance — only used as last hint for empty sniff
    _ = suffix
    return None


def _image_dimensions_ok(raw: bytes) -> tuple[bool, str]:
    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        if w < _MIN_IMAGE_SIDE or h < _MIN_IMAGE_SIDE:
            return False, "image_too_small"
        if w * h > 80_000_000:
            return False, "image_too_large"
        return True, ""
    except Exception:
        return False, "image_unreadable"


def _pdf_looks_sane(raw: bytes) -> tuple[bool, str]:
    if b"%PDF" not in raw[:1024]:
        return False, "not_pdf"
    # Rough polyglot / embedded HTML abuse
    head = raw[:4096].lower()
    if b"<html" in head or b"<script" in head or b"javascript:" in head:
        return False, "pdf_suspicious_content"
    if len(raw) < _MIN_BYTES:
        return False, "file_too_small"
    return True, ""


def extract_document_text(raw: bytes, filename: str = "") -> dict[str, Any]:
    try:
        from backend.app.platform.documents.ocr_pipeline import extract_text_from_bytes

        return extract_text_from_bytes(raw, filename)
    except Exception as exc:
        return {"text": "", "engines": [], "error": str(exc)}


def _score_type_match(doc_type: str, text: str) -> tuple[float, list[str]]:
    patterns = _TYPE_PATTERNS.get(doc_type) or ()
    if not patterns:
        return 0.5, ["no_type_patterns"]
    if not text or text.startswith("[binary"):
        return 0.0, ["no_extractable_text"]
    hits: list[str] = []
    matched = 0
    for pat in patterns:
        if pat.search(text):
            matched += 1
            hits.append(pat.pattern[:48])
    score = matched / max(len(patterns), 1)
    if _JUNK_HINTS.search(text):
        score = min(score, 0.15)
        hits.append("junk_text")
    return score, hits


def verify_worker_document_upload(
    *,
    doc_type: str,
    filename: str,
    claimed_mime: str,
    file_data: bytes,
    encrypted: bool = False,
) -> dict[str, Any]:
    """Return a verification verdict.

    Keys: ok, status (accepted|rejected), score, mime, reasons, message, details
    """
    reasons: list[str] = []
    details: dict[str, Any] = {"docType": doc_type, "filename": filename}

    if not verification_enabled():
        return {
            "ok": True,
            "status": "skipped",
            "score": 1.0,
            "mime": claimed_mime,
            "reasons": ["verification_disabled"],
            "message": "",
            "details": details,
        }

    if not file_data:
        return _reject("empty_file", 0.0, reasons, details, "Die Datei ist leer.")

    # Malware / hostile content (static + optional ClamAV)
    try:
        from backend.app.platform.documents.malware_scan import scan_upload_bytes

        malware = scan_upload_bytes(
            file_data,
            filename=filename,
            mime=claimed_mime,
            encrypted=bool(encrypted),
        )
        details["malwareScan"] = {
            "engine": malware.get("engine"),
            "threats": malware.get("threats") or [],
            "reasons": malware.get("reasons") or [],
        }
        if not malware.get("ok"):
            return _reject(
                "malware_detected",
                0.0,
                reasons + list(malware.get("threats") or []) + ["malware_detected"],
                details,
                str(malware.get("message") or "Verdächtiger Inhalt — Upload abgelehnt."),
            )
    except Exception as exc:
        details["malwareScan"] = {"engine": "error", "error": str(exc)[:120]}

    if len(file_data) < _MIN_BYTES and not encrypted:
        return _reject(
            "file_too_small",
            0.0,
            reasons + ["file_too_small"],
            details,
            "Die Datei ist zu klein, um ein echtes Dokument zu sein.",
        )

    if encrypted:
        # Ciphertext cannot be OCR'd; malware static/ClamAV already ran above.
        return {
            "ok": True,
            "status": "accepted_encrypted",
            "score": 0.5,
            "mime": claimed_mime,
            "reasons": ["e2e_encrypted_skip_content"],
            "message": "",
            "details": details,
        }

    sniffed = sniff_mime(file_data, filename)
    details["sniffedMime"] = sniffed
    details["claimedMime"] = claimed_mime
    if not sniffed:
        return _reject(
            "unrecognized_file_signature",
            0.0,
            reasons + ["bad_magic"],
            details,
            "Dateisignatur ungültig — nur PDF/JPEG/PNG/WEBP als Dokument erlaubt.",
        )
    if sniffed not in WORKER_DOC_ALLOWED_MIMES:
        return _reject(
            "invalid_document_mime",
            0.0,
            reasons + ["mime_not_allowed_for_docs"],
            details,
            "Für Mitarbeiterdokumente sind nur PDF und Bilder (JPEG/PNG/WEBP) erlaubt.",
        )
    # Client claimed a different family than bytes → reject
    claimed = (claimed_mime or "").lower().split(";")[0].strip()
    if claimed and claimed in WORKER_DOC_ALLOWED_MIMES and claimed != sniffed:
        # jpeg vs jpg alias already normalized; reject hard mismatches
        if not (
            {claimed, sniffed} <= {"image/jpeg", "image/jpg"}
            or claimed == sniffed
        ):
            return _reject(
                "mime_mismatch",
                0.1,
                reasons + ["client_mime_mismatch"],
                details,
                "Der Dateityp stimmt nicht mit dem Inhalt überein.",
            )

    if sniffed == "application/pdf":
        ok_pdf, pdf_reason = _pdf_looks_sane(file_data)
        if not ok_pdf:
            return _reject(pdf_reason, 0.0, reasons + [pdf_reason], details, "PDF ungültig oder verdächtig.")
    else:
        ok_img, img_reason = _image_dimensions_ok(file_data)
        if not ok_img:
            return _reject(
                img_reason,
                0.0,
                reasons + [img_reason],
                details,
                "Bild ungültig oder zu klein (kein brauchbares Dokumentfoto).",
            )
        if len(file_data) > _MAX_IMAGE_BYTES_DEFAULT:
            return _reject(
                "file_too_large",
                0.0,
                reasons + ["file_too_large"],
                details,
                "Bilddatei zu groß.",
            )

    # Content-type match via OCR / PDF text
    extracted = extract_document_text(file_data, filename)
    text = str(extracted.get("text") or "")
    engines = extracted.get("engines") or []
    details["ocrEngines"] = engines
    details["textPreview"] = text[:240]
    score, hits = _score_type_match(doc_type, text)
    details["patternHits"] = hits
    reasons.extend(hits[:5])

    high = doc_type in HIGH_ASSURANCE_DOC_TYPES
    if doc_type == "sonstiges":
        # Soft: magic + size enough
        return {
            "ok": True,
            "status": "accepted",
            "score": max(score, 0.6),
            "mime": sniffed,
            "reasons": reasons or ["format_ok"],
            "message": "",
            "details": details,
        }

    if high:
        threshold = 0.34 if len(_TYPE_PATTERNS.get(doc_type) or ()) > 1 else 0.5
        if score >= threshold:
            return {
                "ok": True,
                "status": "accepted",
                "score": score,
                "mime": sniffed,
                "reasons": reasons or ["type_match"],
                "message": "",
                "details": details,
            }
        if not engines or not text or text.startswith("[binary"):
            if verification_strict():
                return _reject(
                    "document_unreadable",
                    score,
                    reasons + ["unreadable"],
                    details,
                    "Dokument nicht lesbar — bitte klares Foto/PDF der Originalurkunde hochladen "
                    "(Personalausweis, Reisepass, Geburtsurkunde o. ä.).",
                )
            return {
                "ok": True,
                "status": "needs_review",
                "score": score,
                "mime": sniffed,
                "reasons": reasons + ["needs_manual_review"],
                "message": "Inhalt konnte nicht automatisch geprüft werden — manuelle Freigabe nötig.",
                "details": details,
            }
        if verification_strict():
            return _reject(
                "document_type_mismatch",
                score,
                reasons + ["type_mismatch"],
                details,
                f"Inhalt passt nicht zum Dokumenttyp „{doc_type}“. "
                "Bitte die korrekte Urkunde/Identitätsdokument hochladen.",
            )
        return {
            "ok": True,
            "status": "needs_review",
            "score": score,
            "mime": sniffed,
            "reasons": reasons + ["type_mismatch_soft"],
            "message": "Automatische Prüfung unsicher — manuelle Freigabe nötig.",
            "details": details,
        }

    # Payroll / other known types: warn but accept if format OK and score middling
    if score >= 0.34 or not verification_strict():
        return {
            "ok": True,
            "status": "accepted" if score >= 0.34 else "needs_review",
            "score": score,
            "mime": sniffed,
            "reasons": reasons or ["format_ok"],
            "message": "" if score >= 0.34 else "Typ unsicher — bitte prüfen.",
            "details": details,
        }
    return _reject(
        "document_type_mismatch",
        score,
        reasons + ["type_mismatch"],
        details,
        "Inhalt passt nicht zum gewählten Dokumenttyp.",
    )


def _reject(
    code: str,
    score: float,
    reasons: list[str],
    details: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "rejected",
        "score": float(score or 0),
        "mime": details.get("sniffedMime"),
        "error": code,
        "reasons": reasons,
        "message": message,
        "details": details,
    }


def counts_as_compliance_evidence(verification_status: str | None) -> bool:
    """Only accepted (or legacy empty) docs satisfy required-document unlocks."""
    status = str(verification_status or "").strip().lower()
    if not status:
        return True  # legacy rows before verification columns
    return status in {"accepted", "accepted_encrypted", "skipped"}
