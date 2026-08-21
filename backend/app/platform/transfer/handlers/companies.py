"""Companies + subcompanies handlers."""
from __future__ import annotations

from typing import Any

from .base import (
    ApplyContext,
    DomainResult,
    decide_row_action,
    fetch_by_id,
    fingerprint_match,
    g,
)


COMPANY_FIELDS = [
    ("name",),
    ("contact",),
    ("billing_email", "billingEmail"),
    ("document_email", "documentEmail"),
    ("access_host", "accessHost"),
    ("branding_preset", "brandingPreset"),
    ("plan",),
    ("status",),
]


def apply_companies(ctx: ApplyContext, rows: list[dict[str, Any]]) -> DomainResult:
    result = DomainResult(domain="companies")
    pending: list[tuple] = []
    for item in rows:
        cid = str(g(item, "id", default="") or ctx.company_id).strip()
        if not cid:
            result.skipped_invalid += 1
            continue
        existing = fetch_by_id(ctx.db, "companies", cid)
        same = bool(existing) and fingerprint_match(existing, item, COMPANY_FIELDS)
        action = decide_row_action(exists=bool(existing), same=same, merge_mode=ctx.merge_mode)
        if action == "unchanged":
            result.unchanged += 1
            continue
        if action == "skip":
            result.conflicts += 1
            result.conflict_ids.append(cid)
            continue
        if action == "fail":
            result.conflicts += 1
            result.conflict_ids.append(cid)
            result.error = f"conflict:companies:{cid}"
            return result
        pending.append(
            (
                cid,
                str(g(item, "name", default="")),
                str(g(item, "contact", default="")),
                str(g(item, "billing_email", "billingEmail", default="")),
                str(g(item, "document_email", "documentEmail", default="")),
                str(g(item, "access_host", "accessHost", default="")),
                str(g(item, "branding_preset", "brandingPreset", default="construction") or "construction"),
                str(g(item, "plan", default="professional") or "professional"),
                str(g(item, "status", default="aktiv") or "aktiv"),
                g(item, "deleted_at", "deletedAt", default=None),
            )
        )
        result.accepted += 1
    if not ctx.dry_run and pending:
        ctx.db.executemany(
            """
            INSERT OR REPLACE INTO companies
            (id, name, contact, billing_email, document_email, access_host, branding_preset, plan, status, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            pending,
        )
    return result


SUB_FIELDS = [("company_id", "companyId"), ("name",), ("contact",), ("status",)]


def apply_subcompanies(ctx: ApplyContext, rows: list[dict[str, Any]]) -> DomainResult:
    result = DomainResult(domain="subcompanies")
    pending: list[tuple] = []
    for item in rows:
        sid = str(g(item, "id", default="")).strip()
        cid = str(g(item, "company_id", "companyId", default=ctx.company_id) or ctx.company_id).strip()
        if not sid:
            result.skipped_invalid += 1
            continue
        existing = fetch_by_id(ctx.db, "subcompanies", sid)
        same = bool(existing) and fingerprint_match(existing, {**item, "company_id": cid}, SUB_FIELDS)
        action = decide_row_action(exists=bool(existing), same=same, merge_mode=ctx.merge_mode)
        if action == "unchanged":
            result.unchanged += 1
            continue
        if action == "skip":
            result.conflicts += 1
            result.conflict_ids.append(sid)
            continue
        if action == "fail":
            result.conflicts += 1
            result.conflict_ids.append(sid)
            result.error = f"conflict:subcompanies:{sid}"
            return result
        pending.append(
            (
                sid,
                cid,
                str(g(item, "name", default="")),
                str(g(item, "contact", default="")),
                str(g(item, "status", default="aktiv") or "aktiv"),
                g(item, "deleted_at", "deletedAt", default=None),
            )
        )
        result.accepted += 1
    if not ctx.dry_run and pending:
        ctx.db.executemany(
            """
            INSERT OR REPLACE INTO subcompanies
            (id, company_id, name, contact, status, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            pending,
        )
    return result
