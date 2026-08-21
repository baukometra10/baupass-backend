"""Contract templates + employment contracts (+ optional PDF files)."""
from __future__ import annotations

from typing import Any

from ..archive import write_file_under
from .base import (
    ApplyContext,
    DomainResult,
    contracts_root,
    decide_row_action,
    fetch_by_id,
    fingerprint_match,
    g,
    utc_now_iso,
)


TEMPLATE_FIELDS = [
    ("company_id", "companyId"),
    ("template_key", "templateKey"),
    ("contract_type", "contractType"),
    ("name",),
    ("language",),
]


def apply_contract_templates(ctx: ApplyContext, rows: list[dict[str, Any]]) -> DomainResult:
    result = DomainResult(domain="contract_templates")
    pending: list[tuple] = []
    for item in rows:
        tid = str(g(item, "id", default="")).strip()
        cid = str(g(item, "company_id", "companyId", default=ctx.company_id) or ctx.company_id).strip()
        if not tid:
            result.skipped_invalid += 1
            continue
        existing = fetch_by_id(ctx.db, "contract_templates", tid)
        same = bool(existing) and fingerprint_match(existing, {**item, "company_id": cid}, TEMPLATE_FIELDS)
        action = decide_row_action(exists=bool(existing), same=same, merge_mode=ctx.merge_mode)
        if action == "unchanged":
            result.unchanged += 1
            continue
        if action == "skip":
            result.conflicts += 1
            result.conflict_ids.append(tid)
            continue
        if action == "fail":
            result.conflicts += 1
            result.conflict_ids.append(tid)
            result.error = f"conflict:contract_templates:{tid}"
            return result
        pending.append(
            (
                tid,
                cid,
                str(g(item, "template_key", "templateKey", default="custom")),
                str(g(item, "contract_type", "contractType", default="employment")),
                str(g(item, "name", default="")),
                str(g(item, "language", default="de") or "de"),
                str(g(item, "body_template", "bodyTemplate", default="")),
                str(g(item, "guidance_text", "guidanceText", default="")),
                str(g(item, "required_fields_json", "requiredFieldsJson", default="[]") or "[]"),
                int(g(item, "active", default=1) or 1),
                str(g(item, "created_at", "createdAt", default=utc_now_iso())),
                str(g(item, "updated_at", "updatedAt", default=utc_now_iso())),
                str(g(item, "created_by_user_id", "createdByUserId", default=ctx.actor_user_id or "")),
            )
        )
        result.accepted += 1
    if not ctx.dry_run and pending:
        try:
            ctx.db.executemany(
                """
                INSERT OR REPLACE INTO contract_templates (
                    id, company_id, template_key, contract_type, name, language, body_template, guidance_text,
                    required_fields_json, active, created_at, updated_at, created_by_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                pending,
            )
        except Exception as exc:
            result.error = f"contract_templates:{exc}"
            result.accepted = 0
    return result


CONTRACT_FIELDS = [
    ("company_id", "companyId"),
    ("worker_id", "workerId"),
    ("contract_type", "contractType"),
    ("title",),
    ("status",),
    ("final_text", "finalText"),
]


def apply_employment_contracts(ctx: ApplyContext, rows: list[dict[str, Any]]) -> DomainResult:
    result = DomainResult(domain="employment_contracts")
    pending: list[tuple] = []
    for item in rows:
        eid = str(g(item, "id", default="")).strip()
        cid = str(g(item, "company_id", "companyId", default=ctx.company_id) or ctx.company_id).strip()
        if not eid:
            result.skipped_invalid += 1
            continue
        pdf_path = str(g(item, "pdf_file_path", "pdfFilePath", default="") or "")
        for rel in (f"contracts/{eid}.pdf", f"contracts/{eid}/contract.pdf"):
            if rel in ctx.package_files:
                if not ctx.dry_run:
                    stored = write_file_under(contracts_root() / cid, f"{eid}.pdf", ctx.package_files[rel])
                    pdf_path = str(stored)
                    ctx.written_files[rel] = pdf_path
                else:
                    pdf_path = f"pending:{rel}"
                break
        existing = fetch_by_id(ctx.db, "employment_contracts", eid)
        same = bool(existing) and fingerprint_match(existing, {**item, "company_id": cid}, CONTRACT_FIELDS)
        action = decide_row_action(exists=bool(existing), same=same, merge_mode=ctx.merge_mode)
        if action == "unchanged":
            result.unchanged += 1
            continue
        if action == "skip":
            result.conflicts += 1
            result.conflict_ids.append(eid)
            continue
        if action == "fail":
            result.conflicts += 1
            result.conflict_ids.append(eid)
            result.error = f"conflict:employment_contracts:{eid}"
            return result
        pending.append(
            (
                eid,
                cid,
                g(item, "worker_id", "workerId", default=None),
                g(item, "template_id", "templateId", default=None),
                str(g(item, "contract_type", "contractType", default="employment") or "employment"),
                str(g(item, "title", default="")),
                str(g(item, "language", default="de") or "de"),
                str(g(item, "status", default="draft") or "draft"),
                str(g(item, "input_json", "inputJson", default="{}") or "{}"),
                str(g(item, "ai_prompt", "aiPrompt", default="")),
                str(g(item, "draft_text", "draftText", default="")),
                str(g(item, "final_text", "finalText", default="")),
                pdf_path,
                str(g(item, "created_by_user_id", "createdByUserId", default=ctx.actor_user_id or "import")),
                str(g(item, "created_at", "createdAt", default=utc_now_iso())),
                str(g(item, "updated_at", "updatedAt", default=utc_now_iso())),
            )
        )
        result.accepted += 1
    if not ctx.dry_run and pending:
        ctx.db.executemany(
            """
            INSERT OR REPLACE INTO employment_contracts (
                id, company_id, worker_id, template_id, contract_type, title, language, status,
                input_json, ai_prompt, draft_text, final_text, pdf_file_path,
                created_by_user_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            pending,
        )
    return result
