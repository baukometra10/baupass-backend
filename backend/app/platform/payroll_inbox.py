"""Heuristics for payroll / DATEV document routing in the mail inbox."""
from __future__ import annotations

import re
from typing import Any

from backend.app.platform.worker_documents import normalize_doc_type

_CONFIDENCE_RANK = {"": 0, "medium": 1, "high": 2}

_PAYROLL_HINT = re.compile(
    r"\b(lohn|gehalt|payroll|payslip|salary|abrechnung|entgelt|verdienst|datev|lohnjournal)\b",
    re.IGNORECASE,
)
_ID_DOC_HINT = re.compile(
    r"\b(ausweis|personalausweis|reisepass|passport|id[\s-]?card|identit)\b",
    re.IGNORECASE,
)
_MINLOHN_DOC_HINT = re.compile(
    r"\b(mindestlohn|minimum[\s-]?wage|lohnnachweis|mindestlohnnachweis)\b",
    re.IGNORECASE,
)
_GEHALT_HINT = re.compile(r"\b(gehalt|salary|gehalts)\b", re.IGNORECASE)
_DATEV_FROM = re.compile(r"datev|lohnbuchhaltung|payroll", re.IGNORECASE)


def suggest_doc_type_from_email(
    *,
    filename: str = "",
    subject: str = "",
    from_addr: str = "",
    body_text: str = "",
) -> dict[str, Any]:
    """Return suggested worker document type for an inbox attachment."""
    name = str(filename or "").strip()
    subj = str(subject or "").strip()
    sender = str(from_addr or "").strip()
    body = str(body_text or "").strip()[:4000]
    combined = " ".join(part for part in (name, subj, sender, body) if part).lower()

    if not combined:
        return {"docType": "", "confidence": "", "reason": ""}

    is_pdf = name.lower().endswith(".pdf") or "pdf" in combined

    if _ID_DOC_HINT.search(combined):
        return {
            "docType": normalize_doc_type("personalausweis"),
            "confidence": "high" if is_pdf else "medium",
            "reason": "id_document_keywords",
        }
    if _MINLOHN_DOC_HINT.search(combined):
        return {
            "docType": normalize_doc_type("mindestlohnnachweis"),
            "confidence": "high" if is_pdf else "medium",
            "reason": "mindestlohn_keywords",
        }

    payroll_hit = bool(_PAYROLL_HINT.search(combined))
    datev_sender = bool(_DATEV_FROM.search(sender))

    if not payroll_hit and not datev_sender:
        return {"docType": "", "confidence": "", "reason": ""}

    doc_type = "gehaltsabrechnung" if _GEHALT_HINT.search(combined) else "lohnabrechnung"
    doc_type = normalize_doc_type(doc_type)

    if datev_sender and is_pdf:
        confidence = "high"
        reason = "datev_sender_pdf"
    elif payroll_hit and is_pdf:
        confidence = "high"
        reason = "payroll_filename_pdf"
    elif payroll_hit:
        confidence = "medium"
        reason = "payroll_keywords"
    else:
        confidence = "medium"
        reason = "datev_sender"

    return {"docType": doc_type, "confidence": confidence, "reason": reason}


def suggest_doc_type_from_pdf_bytes(
    raw: bytes,
    *,
    filename: str = "",
    subject: str = "",
    from_addr: str = "",
) -> dict[str, Any]:
    """OCR / PDF text extraction for payroll classification."""
    if not raw:
        return {"docType": "", "confidence": "", "reason": ""}
    extracted: dict[str, Any] = {}
    try:
        from backend.app.platform.documents.ocr_pipeline import extract_text_from_bytes

        extracted = extract_text_from_bytes(raw, filename or "document.pdf")
    except Exception:
        extracted = {}
    body_text = str(extracted.get("text") or "")
    if not body_text.strip():
        return {"docType": "", "confidence": "", "reason": ""}
    result = suggest_doc_type_from_email(
        filename=filename,
        subject=subject,
        from_addr=from_addr,
        body_text=body_text,
    )
    if result.get("docType"):
        result["reason"] = f"pdf_{result.get('reason') or 'ocr'}"
        engines = extracted.get("engines")
        if isinstance(engines, list) and engines:
            result["ocrEngines"] = engines
    return result


def _merge_suggestion(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    if not secondary.get("docType"):
        return primary
    if not primary.get("docType"):
        return secondary
    if _CONFIDENCE_RANK.get(str(secondary.get("confidence") or ""), 0) > _CONFIDENCE_RANK.get(
        str(primary.get("confidence") or ""), 0
    ):
        return secondary
    return primary


def _apply_suggestion_to_row(row: dict[str, Any], suggestion: dict[str, Any]) -> None:
    if not suggestion.get("docType"):
        return
    row["suggested_doc_type"] = suggestion["docType"]
    row["suggestedDocType"] = suggestion["docType"]
    row["suggest_confidence"] = suggestion.get("confidence") or ""
    row["suggestConfidence"] = suggestion.get("confidence") or ""
    row["suggest_reason"] = suggestion.get("reason") or ""
    row["suggestReason"] = suggestion.get("reason") or ""


def enrich_inbox_attachments(
    attachments: list[dict[str, Any]],
    *,
    subject: str = "",
    from_addr: str = "",
    body_text: str = "",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for att in attachments:
        row = dict(att)
        if row.get("assigned_worker_id") or row.get("assigned_doc_type"):
            out.append(row)
            continue
        suggestion = suggest_doc_type_from_email(
            filename=str(row.get("filename") or ""),
            subject=subject,
            from_addr=from_addr,
            body_text=body_text,
        )
        _apply_suggestion_to_row(row, suggestion)
        out.append(row)
    return out


def enrich_inbox_attachments_with_pdf_scan(
    db,
    attachments: list[dict[str, Any]],
    inbox_id: str,
    *,
    subject: str = "",
    from_addr: str = "",
    body_text: str = "",
) -> list[dict[str, Any]]:
    """Email heuristics + optional PDF text scan per attachment."""
    enriched = enrich_inbox_attachments(
        attachments,
        subject=subject,
        from_addr=from_addr,
        body_text=body_text,
    )
    for row in enriched:
        if row.get("assigned_worker_id") or row.get("assigned_doc_type"):
            continue
        att_id = str(row.get("id") or "").strip()
        if not att_id:
            continue
        blob_row = db.execute(
            "SELECT file_data, filename, content_type FROM email_attachments WHERE id = ? AND inbox_id = ?",
            (att_id, inbox_id),
        ).fetchone()
        if not blob_row or not blob_row["file_data"]:
            continue
        filename = str(blob_row["filename"] or "")
        content_type = str(blob_row["content_type"] or "").lower()
        if not (filename.lower().endswith(".pdf") or "pdf" in content_type):
            continue
        file_data = blob_row["file_data"]
        if isinstance(file_data, memoryview):
            file_data = file_data.tobytes()
        elif isinstance(file_data, bytearray):
            file_data = bytes(file_data)
        elif isinstance(file_data, str):
            file_data = file_data.encode("utf-8", errors="replace")
        else:
            file_data = bytes(file_data)
        pdf_hint = suggest_doc_type_from_pdf_bytes(
            file_data,
            filename=filename,
            subject=subject,
            from_addr=from_addr,
        )
        email_hint = {
            "docType": row.get("suggestedDocType") or row.get("suggested_doc_type") or "",
            "confidence": row.get("suggestConfidence") or row.get("suggest_confidence") or "",
            "reason": row.get("suggestReason") or row.get("suggest_reason") or "",
        }
        merged = _merge_suggestion(email_hint, pdf_hint)
        _apply_suggestion_to_row(row, merged)
    return enriched
