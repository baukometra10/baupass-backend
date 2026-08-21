"""Workers handler incl. photo file restore."""
from __future__ import annotations

import base64
from typing import Any

from ..archive import write_file_under
from .base import (
    ApplyContext,
    DomainResult,
    decide_row_action,
    docs_root,
    fetch_by_id,
    fingerprint_match,
    g,
)


WORKER_FIELDS = [
    ("company_id", "companyId"),
    ("first_name", "firstName"),
    ("last_name", "lastName"),
    ("insurance_number", "insuranceNumber"),
    ("worker_type", "workerType"),
    ("role",),
    ("site",),
    ("valid_until", "validUntil"),
    ("status",),
    ("badge_id", "badgeId"),
]


def _resolve_photo(ctx: ApplyContext, worker_id: str, item: dict[str, Any]) -> tuple[str, str | None]:
    existing_photo = str(g(item, "photo_data", "photoData", default="") or "")
    packed = None
    rel_hit = ""
    for rel in (
        f"worker_photos/{worker_id}.jpg",
        f"worker_photos/{worker_id}.jpeg",
        f"worker_photos/{worker_id}.png",
        f"worker_photos/{worker_id}.webp",
        f"workers/{worker_id}/photo.jpg",
        f"workers/{worker_id}/photo.png",
    ):
        if rel in ctx.package_files:
            packed = ctx.package_files[rel]
            rel_hit = rel
            break
    if packed is None:
        return existing_photo, None
    ext = ".jpg"
    if rel_hit.endswith(".png"):
        ext = ".png"
    elif rel_hit.endswith(".webp"):
        ext = ".webp"
    mime = "image/jpeg" if ext == ".jpg" else ("image/png" if ext == ".png" else "image/webp")
    if not ctx.dry_run:
        stored = write_file_under(docs_root() / worker_id / "photos", f"portrait{ext}", packed)
        ctx.written_files[rel_hit] = str(stored)
    b64 = base64.b64encode(packed).decode("ascii")
    return f"data:{mime};base64,{b64}", rel_hit


def apply_workers(ctx: ApplyContext, rows: list[dict[str, Any]]) -> DomainResult:
    result = DomainResult(domain="workers")
    pending: list[tuple] = []
    for item in rows:
        wid = str(g(item, "id", default="")).strip()
        cid = str(g(item, "company_id", "companyId", default=ctx.company_id) or ctx.company_id).strip()
        if not wid:
            result.skipped_invalid += 1
            continue
        photo, _rel = _resolve_photo(ctx, wid, item)
        existing = fetch_by_id(ctx.db, "workers", wid)
        same = bool(existing) and fingerprint_match(existing, {**item, "company_id": cid}, WORKER_FIELDS)
        if same and existing and photo:
            if str(existing.get("photo_data") or "") != photo:
                same = False
        action = decide_row_action(exists=bool(existing), same=same, merge_mode=ctx.merge_mode)
        if action == "unchanged":
            result.unchanged += 1
            continue
        if action == "skip":
            result.conflicts += 1
            result.conflict_ids.append(wid)
            continue
        if action == "fail":
            result.conflicts += 1
            result.conflict_ids.append(wid)
            result.error = f"conflict:workers:{wid}"
            return result
        pin_hash = ""
        if existing and action == "replace":
            pin_hash = str(existing.get("badge_pin_hash") or "")
        pending.append(
            (
                wid,
                cid,
                g(item, "subcompany_id", "subcompanyId", default=None),
                str(g(item, "first_name", "firstName", default="")),
                str(g(item, "last_name", "lastName", default="")),
                str(g(item, "insurance_number", "insuranceNumber", default="")),
                str(g(item, "worker_type", "workerType", default="mitarbeiter") or "mitarbeiter"),
                str(g(item, "role", default="")),
                str(g(item, "site", default="")),
                str(g(item, "valid_until", "validUntil", default="")),
                str(g(item, "visitor_company", "visitorCompany", default="")),
                str(g(item, "visit_purpose", "visitPurpose", default="")),
                str(g(item, "host_name", "hostName", default="")),
                g(item, "visit_end_at", "visitEndAt", default=None),
                str(g(item, "status", default="aktiv") or "aktiv"),
                photo,
                str(g(item, "badge_id", "badgeId", default="")),
                pin_hash,
                g(item, "physical_card_id", "physicalCardId", default=None),
                g(item, "deleted_at", "deletedAt", default=None),
            )
        )
        result.accepted += 1
    if not ctx.dry_run and pending:
        ctx.db.executemany(
            """
            INSERT OR REPLACE INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number, worker_type, role, site, valid_until,
                visitor_company, visit_purpose, host_name, visit_end_at, status, photo_data, badge_id, badge_pin_hash, physical_card_id, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            pending,
        )
    return result
