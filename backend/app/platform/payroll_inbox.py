"""Heuristics for payroll / DATEV document routing in the mail inbox."""
from __future__ import annotations

import re
from typing import Any

from backend.app.platform.worker_documents import normalize_doc_type

_PAYROLL_HINT = re.compile(
    r"\b(lohn|gehalt|payroll|payslip|salary|abrechnung|entgelt|verdienst|datev|lohnjournal)\b",
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
        if suggestion.get("docType"):
            row["suggested_doc_type"] = suggestion["docType"]
            row["suggestedDocType"] = suggestion["docType"]
            row["suggest_confidence"] = suggestion.get("confidence") or ""
            row["suggestConfidence"] = suggestion.get("confidence") or ""
            row["suggest_reason"] = suggestion.get("reason") or ""
            row["suggestReason"] = suggestion.get("reason") or ""
        out.append(row)
    return out
