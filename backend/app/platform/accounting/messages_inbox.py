"""WorkPass Lohn → Platform accounting.message inbox (pull + webhook + ack)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from . import repository as repo
from .auth import sign_payload, verify_signature
from .platform_link import get_platform_link, resolve_master_api_keys
from .schema import ensure_accounting_schema

MESSAGES_PENDING_PATH = "/v1/messages/pending"
MESSAGES_ACK_PATH = "/v1/messages/ack"
EVENT_ACCOUNTING_MESSAGE = "accounting.message"
_MISSING_DATA_KINDS = frozenset(
    {
        "missing_data",
        "missing_employee_data",
        "employee_data",
        "data_gap",
        "stammdaten",
        "incomplete_employee",
    }
)


def resolve_company_worker(db, company_id: str, raw_id: str) -> dict[str, Any] | None:
    """
    Map Lohn employeeId / workerId / badge to a SUPPIX worker row.
    Returns id, names, badgeId, displayName — or None.
    """
    company_id = str(company_id or "").strip()
    raw = str(raw_id or "").strip()
    if not company_id or not raw:
        return None
    try:
        row = db.execute(
            """
            SELECT id, first_name, last_name, badge_id, badge_id_lookup, physical_card_id,
                   insurance_number, contact_email
            FROM workers
            WHERE company_id = ? AND deleted_at IS NULL
              AND (
                    id = ?
                 OR lower(COALESCE(badge_id, '')) = lower(?)
                 OR lower(COALESCE(badge_id_lookup, '')) = lower(?)
                 OR lower(COALESCE(physical_card_id, '')) = lower(?)
                 OR lower(COALESCE(insurance_number, '')) = lower(?)
                 OR lower(COALESCE(contact_email, '')) = lower(?)
              )
            ORDER BY CASE WHEN id = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (company_id, raw, raw, raw, raw, raw, raw, raw),
        ).fetchone()
    except Exception:
        row = None
    if not row:
        return None
    first = str(row["first_name"] or "").strip()
    last = str(row["last_name"] or "").strip()
    display = f"{first} {last}".strip() or str(row["badge_id"] or row["id"] or "").strip()
    return {
        "id": str(row["id"] or "").strip(),
        "firstName": first,
        "lastName": last,
        "badgeId": str(row["badge_id"] or "").strip(),
        "displayName": display,
    }


def annotate_text_with_worker_name(text: str, *, worker_id: str, display_name: str) -> str:
    """If body/subject only shows a raw ID, append the human name once."""
    raw = str(text or "")
    wid = str(worker_id or "").strip()
    name = str(display_name or "").strip()
    if not raw or not wid or not name:
        return raw
    if name.lower() in raw.lower():
        return raw
    # Common patterns: bare id, "Mitarbeiter <id>", "Employee <id>"
    if wid in raw:
        return raw.replace(wid, f"{name} ({wid})", 1)
    return f"{raw} — {name} ({wid})"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _master_key(link: dict[str, Any] | None = None) -> str:
    from .platform_link import primary_master_api_key

    return primary_master_api_key(link)


def verify_platform_webhook_auth(
    db,
    *,
    headers: dict[str, str],
    body: bytes,
    company_id: str = "",
) -> dict[str, Any]:
    """
    Auth for WORKPASS_PLATFORM_WEBHOOK_URL inbound posts from Lohn.
    Accepts master key (X-WorkPass-Webhook-Key / X-WorkPass-Key / Bearer) or per-company accounting key.
    """
    from .auth import authenticate_accounting_request

    hdr = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    key = (
        hdr.get("x-workpass-webhook-key")
        or hdr.get("x-workpass-key")
        or hdr.get("x-workpass-master-key")
        or hdr.get("x-accounting-key")
        or ""
    ).strip()
    auth = hdr.get("authorization") or ""
    if not key and auth.lower().startswith("bearer "):
        key = auth[7:].strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()

    link = get_platform_link(db)
    masters = resolve_master_api_keys(link)
    ts = (hdr.get("x-suppix-timestamp") or "").strip()
    sig = (hdr.get("x-suppix-signature") or "").strip()

    matched_master = next((m for m in masters if key and key == m), None)
    if matched_master:
        if sig and not verify_signature(matched_master, timestamp=ts, body=body or b"", signature=sig):
            return {"ok": False, "error": "invalid_signature"}
        return {"ok": True, "auth": "master", "companyId": (company_id or "").strip()}

    company_id = (
        company_id
        or hdr.get("x-workpass-company-id")
        or hdr.get("x-company-id")
        or ""
    ).strip()
    if company_id and key:
        integ = authenticate_accounting_request(
            db,
            company_id=company_id,
            api_key=key,
            timestamp=ts,
            signature=sig,
            body=body or b"",
            require_signature=bool(sig),
        )
        if integ:
            return {"ok": True, "auth": "accounting", "companyId": company_id, "integration": integ}

    if not key:
        return {"ok": False, "error": "unauthorized", "hint": "Send X-WorkPass-Key or X-Accounting-Key"}
    return {"ok": False, "error": "unauthorized"}


def _normalize_message_item(item: dict[str, Any], *, default_company: str = "") -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    external_id = str(
        item.get("id")
        or item.get("messageId")
        or item.get("externalId")
        or item.get("external_id")
        or ""
    ).strip()
    company_id = str(
        item.get("companyId")
        or item.get("company_id")
        or (item.get("company") or {}).get("id")
        or default_company
        or ""
    ).strip()
    if not company_id:
        return None
    if not external_id:
        import hashlib

        fingerprint = json.dumps(
            {
                "c": company_id,
                "s": item.get("subject") or item.get("title") or "",
                "b": (item.get("body") or item.get("message") or item.get("text") or "")[:200],
                "p": item.get("period") or "",
                "w": item.get("workerId") or item.get("employeeId") or "",
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        external_id = "gen-" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
    kind = str(
        item.get("kind")
        or item.get("type")
        or item.get("category")
        or item.get("messageType")
        or ""
    ).strip()
    subject = str(item.get("subject") or item.get("title") or item.get("headline") or "").strip()
    body = str(item.get("body") or item.get("message") or item.get("text") or item.get("detail") or "").strip()
    if not subject and body:
        subject = body[:80]
    if not subject:
        subject = kind or EVENT_ACCOUNTING_MESSAGE
    worker_id = str(item.get("workerId") or item.get("employeeId") or item.get("worker_id") or "").strip()
    period = str(item.get("period") or "").strip()[:7]
    event = str(item.get("event") or EVENT_ACCOUNTING_MESSAGE).strip() or EVENT_ACCOUNTING_MESSAGE
    return {
        "externalId": external_id,
        "companyId": company_id,
        "event": event,
        "kind": kind,
        "subject": subject[:300],
        "body": body[:4000],
        "period": period,
        "workerId": worker_id,
        "payload": item,
    }


def upsert_accounting_messages(
    db,
    messages: list[dict[str, Any]],
    *,
    default_company: str = "",
) -> dict[str, Any]:
    ensure_accounting_schema(db)
    created = 0
    updated = 0
    skipped_acked = 0
    ids: list[str] = []
    now = _now()
    for raw in messages or []:
        norm = _normalize_message_item(raw, default_company=default_company)
        if not norm:
            continue
        resolved = resolve_company_worker(db, norm["companyId"], norm.get("workerId") or "")
        if resolved:
            canon = resolved["id"]
            display = resolved["displayName"]
            if canon:
                norm["workerId"] = canon
            if display:
                norm["subject"] = annotate_text_with_worker_name(
                    norm.get("subject") or "",
                    worker_id=canon or str(norm.get("workerId") or ""),
                    display_name=display,
                )
                norm["body"] = annotate_text_with_worker_name(
                    norm.get("body") or "",
                    worker_id=canon or str(norm.get("workerId") or ""),
                    display_name=display,
                )
            # Keep original Lohn id in payload for debugging
            if isinstance(norm.get("payload"), dict):
                norm["payload"] = dict(norm["payload"])
                norm["payload"]["resolvedWorkerId"] = canon
                norm["payload"]["resolvedWorkerName"] = display
        existing = db.execute(
            """
            SELECT id, status, banner_dismissed_at, payload_json, subject, body, kind, period, worker_id
            FROM accounting_messages
            WHERE company_id = ? AND external_id = ?
            LIMIT 1
            """,
            (norm["companyId"], norm["externalId"]),
        ).fetchone()
        payload_json = json.dumps(norm["payload"], ensure_ascii=False)
        if existing:
            existing_status = str(existing["status"] or "").strip().lower()
            # Locally confirmed messages must not reappear when Lohn still lists them pending.
            if existing_status == "acked":
                skipped_acked += 1
                ids.append(str(existing["id"]))
                continue

            try:
                existing_payload = json.loads(existing["payload_json"] or "{}")
            except Exception:
                existing_payload = {}
            if not isinstance(existing_payload, dict):
                existing_payload = {}

            banner_dismissed_at = str(existing["banner_dismissed_at"] or "").strip()
            banner_dismissed = bool(banner_dismissed_at) or bool(
                existing_payload.get("bannerDismissed") or existing_payload.get("banner_dismissed")
            )

            merged_payload = {**existing_payload, **(norm["payload"] if isinstance(norm["payload"], dict) else {})}
            if banner_dismissed:
                # Keep toast dismissed across sync/webhook pulls of the same message.
                merged_payload["bannerDismissed"] = True
                if banner_dismissed_at:
                    merged_payload["bannerDismissedAt"] = banner_dismissed_at
                elif not merged_payload.get("bannerDismissedAt"):
                    merged_payload["bannerDismissedAt"] = now
            else:
                merged_payload.pop("bannerDismissed", None)
                merged_payload.pop("banner_dismissed", None)
                merged_payload.pop("bannerDismissedAt", None)
            payload_json = json.dumps(merged_payload, ensure_ascii=False)

            # Content refresh only — never clear local banner dismiss / never revive acked.
            try:
                if banner_dismissed_at:
                    db.execute(
                        """
                        UPDATE accounting_messages
                        SET event = ?, kind = ?, subject = ?, body = ?, period = ?, worker_id = ?,
                            payload_json = ?, status = 'pending', updated_at = ?, received_at = ?
                        WHERE id = ?
                        """,
                        (
                            norm["event"],
                            norm["kind"],
                            norm["subject"],
                            norm["body"],
                            norm["period"],
                            norm["workerId"],
                            payload_json,
                            now,
                            now,
                            existing["id"],
                        ),
                    )
                else:
                    db.execute(
                        """
                        UPDATE accounting_messages
                        SET event = ?, kind = ?, subject = ?, body = ?, period = ?, worker_id = ?,
                            payload_json = ?, status = 'pending', updated_at = ?,
                            banner_dismissed_at = NULL, received_at = ?
                        WHERE id = ?
                        """,
                        (
                            norm["event"],
                            norm["kind"],
                            norm["subject"],
                            norm["body"],
                            norm["period"],
                            norm["workerId"],
                            payload_json,
                            now,
                            now,
                            existing["id"],
                        ),
                    )
            except Exception:
                db.execute(
                    """
                    UPDATE accounting_messages
                    SET event = ?, kind = ?, subject = ?, body = ?, period = ?, worker_id = ?,
                        payload_json = ?, status = 'pending', updated_at = ?, received_at = ?
                    WHERE id = ?
                    """,
                    (
                        norm["event"],
                        norm["kind"],
                        norm["subject"],
                        norm["body"],
                        norm["period"],
                        norm["workerId"],
                        payload_json,
                        now,
                        now,
                        existing["id"],
                    ),
                )
            updated += 1
            ids.append(str(existing["id"]))
        else:
            mid = f"amsg-{uuid.uuid4().hex[:16]}"
            try:
                db.execute(
                    """
                    INSERT INTO accounting_messages
                    (id, external_id, company_id, event, kind, subject, body, period, worker_id,
                     payload_json, status, received_at, read_at, acked_at, ack_error, updated_at,
                     banner_dismissed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL, '', ?, NULL)
                    """,
                    (
                        mid,
                        norm["externalId"],
                        norm["companyId"],
                        norm["event"],
                        norm["kind"],
                        norm["subject"],
                        norm["body"],
                        norm["period"],
                        norm["workerId"],
                        payload_json,
                        now,
                        now,
                    ),
                )
            except Exception:
                db.execute(
                    """
                    INSERT INTO accounting_messages
                    (id, external_id, company_id, event, kind, subject, body, period, worker_id,
                     payload_json, status, received_at, read_at, acked_at, ack_error, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL, '', ?)
                    """,
                    (
                        mid,
                        norm["externalId"],
                        norm["companyId"],
                        norm["event"],
                        norm["kind"],
                        norm["subject"],
                        norm["body"],
                        norm["period"],
                        norm["workerId"],
                        payload_json,
                        now,
                        now,
                    ),
                )
            created += 1
            ids.append(mid)
        kind_l = (norm["kind"] or "").lower()
        text_l = f"{norm['subject']} {norm['body']}".lower()
        if kind_l in {"missing_data", "missing_employee_data", "employee_data", "data_gap"} or (
            "fehlend" in text_l or "missing" in kind_l
        ):
            fields = []
            payload = norm["payload"] if isinstance(norm["payload"], dict) else {}
            raw_fields = payload.get("missingFields") or payload.get("fields") or []
            if isinstance(raw_fields, list):
                fields = [str(f) for f in raw_fields]
            repo.ingest_lohn_data_alerts(
                db,
                company_id=norm["companyId"],
                period=norm["period"],
                issues=[
                    {
                        "employeeId": norm["workerId"],
                        "workerId": norm["workerId"],
                        "missingFields": fields,
                        "message": norm["body"] or norm["subject"],
                        "externalRef": norm["externalId"],
                        "period": norm["period"],
                    }
                ],
            )
    try:
        db.commit()
    except Exception:
        pass
    return {
        "ok": True,
        "createdCount": created,
        "updatedCount": updated,
        "skippedAckedCount": skipped_acked,
        "ids": ids,
    }


def count_pending_accounting_messages(
    db,
    *,
    company_id: str | None = None,
) -> dict[str, int]:
    """Lightweight unread + toast counts for nav badges (no full payload)."""
    ensure_accounting_schema(db)
    from .schema import _ensure_accounting_message_banner_column

    _ensure_accounting_message_banner_column(db)
    if company_id:
        rows = db.execute(
            """
            SELECT status, banner_dismissed_at, payload_json
            FROM accounting_messages
            WHERE company_id = ? AND status = 'pending'
            """,
            (company_id,),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT status, banner_dismissed_at, payload_json
            FROM accounting_messages
            WHERE status = 'pending'
            """
        ).fetchall()
    unread = 0
    notifications = 0
    for row in rows:
        unread += 1
        banner_dismissed = bool(str(row["banner_dismissed_at"] or "").strip())
        if not banner_dismissed:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                banner_dismissed = bool(payload.get("bannerDismissed") or payload.get("banner_dismissed"))
        if not banner_dismissed:
            notifications += 1
    return {"count": unread, "notificationCount": notifications, "unread": unread}


def dismiss_all_message_banners(
    db,
    *,
    actor_user_id: str = "",
    company_id: str | None = None,
) -> dict[str, Any]:
    """Hide all pending toasts; inbox stays unread."""
    pending = list_pending_accounting_messages(db, company_id=company_id, limit=500)
    dismissed = 0
    for item in pending:
        if not item.get("bannerVisible"):
            continue
        out = dismiss_message_banner(
            db,
            message_id=str(item.get("id") or ""),
            actor_user_id=actor_user_id,
            company_id=company_id,
        )
        if out.get("ok"):
            dismissed += 1
    return {"ok": True, "dismissed": dismissed, "pending": len(pending)}


# Inbox kinds created for "please confirm period handoff" — cleared after Ops confirm/reject.
PERIOD_HANDOFF_MESSAGE_KINDS = frozenset(
    {
        "period_request",
        "payroll.month.requested",
        "employees.list.requested",
        "payroll_month_requested",
        "employees_list_requested",
        "payroll.requested",
        "payroll.batch.requested",
        "hours.requested",
        "abrechnung.requested",
    }
)


def clear_period_handoff_messages(
    db,
    *,
    company_id: str,
    period: str,
    actor_user_id: str = "",
) -> dict[str, Any]:
    """
    After Ops confirms or rejects a period handoff, ack matching inbox messages
    so toasts / unread noise disappear (missing_data / payslip messages stay).
    """
    ensure_accounting_schema(db)
    company_id = str(company_id or "").strip()
    period = str(period or "").strip()[:7]
    if not company_id or not period:
        return {"ok": False, "error": "company_period_required", "cleared": 0, "ids": []}

    rows = db.execute(
        """
        SELECT id, kind, subject, period
        FROM accounting_messages
        WHERE company_id = ? AND status = 'pending' AND period = ?
        """,
        (company_id, period),
    ).fetchall()

    cleared: list[str] = []
    for row in rows:
        kind = str(row["kind"] or "").strip().lower()
        subject = str(row["subject"] or "")
        is_handoff = kind in PERIOD_HANDOFF_MESSAGE_KINDS or subject.startswith("Lohn-Anfrage")
        if not is_handoff:
            continue
        out = ack_message_to_lohn(
            db,
            message_id=str(row["id"]),
            actor_user_id=actor_user_id,
            company_id=company_id,
        )
        if out.get("ok"):
            cleared.append(str(row["id"]))

    return {
        "ok": True,
        "companyId": company_id,
        "period": period,
        "cleared": len(cleared),
        "ids": cleared,
    }


def dismiss_related_data_alerts_for_message(
    db,
    *,
    company_id: str,
    worker_id: str = "",
    period: str = "",
    actor_user_id: str = "",
) -> dict[str, Any]:
    """When a Lohn message is opened, clear matching open missing-data alerts."""
    ensure_accounting_schema(db)
    company_id = str(company_id or "").strip()
    worker_id = str(worker_id or "").strip()
    period = str(period or "").strip()[:7]
    if not company_id:
        return {"ok": True, "dismissed": 0}
    now = _now()
    if worker_id and period:
        cur = db.execute(
            """
            UPDATE lohn_data_alerts
            SET status = 'dismissed', dismissed_at = ?, dismissed_by_user_id = ?, updated_at = ?
            WHERE company_id = ? AND status = 'open'
              AND worker_id = ? AND (period = ? OR period = '' OR period IS NULL)
            """,
            (now, str(actor_user_id or "")[:80], now, company_id, worker_id, period),
        )
    elif worker_id:
        cur = db.execute(
            """
            UPDATE lohn_data_alerts
            SET status = 'dismissed', dismissed_at = ?, dismissed_by_user_id = ?, updated_at = ?
            WHERE company_id = ? AND status = 'open' AND worker_id = ?
            """,
            (now, str(actor_user_id or "")[:80], now, company_id, worker_id),
        )
    else:
        return {"ok": True, "dismissed": 0}
    try:
        db.commit()
    except Exception:
        pass
    return {"ok": True, "dismissed": int(getattr(cur, "rowcount", 0) or 0)}


def list_pending_accounting_messages(
    db,
    *,
    company_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    ensure_accounting_schema(db)
    limit = max(1, min(int(limit or 100), 500))
    if company_id:
        rows = db.execute(
            """
            SELECT m.*, w.first_name, w.last_name
            FROM accounting_messages m
            LEFT JOIN workers w ON w.id = m.worker_id
            WHERE m.company_id = ? AND m.status = 'pending'
            ORDER BY m.received_at DESC
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT m.*, w.first_name, w.last_name
            FROM accounting_messages m
            LEFT JOIN workers w ON w.id = m.worker_id
            WHERE m.status = 'pending'
            ORDER BY m.received_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out = []
    for row in rows:
        data = dict(row)
        try:
            payload = json.loads(data.get("payload_json") or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        banner_dismissed = bool(str(data.get("banner_dismissed_at") or "").strip())
        if not banner_dismissed:
            banner_dismissed = bool(payload.get("bannerDismissed") or payload.get("banner_dismissed"))
        raw_fields = payload.get("missingFields") or payload.get("fields") or []
        if isinstance(raw_fields, str):
            raw_fields = [p.strip() for p in raw_fields.split(",") if p.strip()]
        if not isinstance(raw_fields, list):
            raw_fields = []
        missing_fields = [str(f).strip() for f in raw_fields if str(f).strip()][:40]
        worker_id = str(data.get("worker_id") or payload.get("workerId") or payload.get("employeeId") or "").strip()
        company_for_row = str(data.get("company_id") or company_id or "").strip()
        resolved = resolve_company_worker(db, company_for_row, worker_id) if worker_id else None
        if resolved:
            # Prefer canonical SUPPIX worker id for UI deep-links
            if resolved["id"] and resolved["id"] != worker_id:
                try:
                    db.execute(
                        "UPDATE accounting_messages SET worker_id = ?, updated_at = ? WHERE id = ?",
                        (resolved["id"], _now(), data.get("id")),
                    )
                    db.commit()
                except Exception:
                    pass
                worker_id = resolved["id"]
            first_name = resolved["firstName"] or str(data.get("first_name") or "")
            last_name = resolved["lastName"] or str(data.get("last_name") or "")
            display_name = resolved["displayName"]
        else:
            first_name = str(data.get("first_name") or "")
            last_name = str(data.get("last_name") or "")
            display_name = f"{first_name} {last_name}".strip()
        subject = str(data.get("subject") or "")
        body_text = str(data.get("body") or "")
        if display_name and worker_id:
            subject = annotate_text_with_worker_name(subject, worker_id=worker_id, display_name=display_name)
            body_text = annotate_text_with_worker_name(body_text, worker_id=worker_id, display_name=display_name)
        out.append(
            {
                "id": data.get("id"),
                "externalId": data.get("external_id"),
                "companyId": data.get("company_id"),
                "event": data.get("event") or EVENT_ACCOUNTING_MESSAGE,
                "kind": data.get("kind") or "",
                "subject": subject,
                "body": body_text,
                "period": data.get("period") or "",
                "workerId": worker_id,
                "workerFirstName": first_name,
                "workerLastName": last_name,
                "workerDisplayName": display_name,
                "workerBadgeId": (resolved or {}).get("badgeId") or "",
                "workerResolved": bool(resolved),
                "missingFields": missing_fields,
                "status": data.get("status") or "pending",
                "receivedAt": data.get("received_at"),
                "bannerDismissedAt": data.get("banner_dismissed_at"),
                "bannerVisible": not banner_dismissed,
                "unread": True,
                "payload": payload,
            }
        )
    return out


def dismiss_message_banner(
    db,
    *,
    message_id: str,
    actor_user_id: str = "",
    company_id: str | None = None,
) -> dict[str, Any]:
    """
    Hide dashboard notification only — message stays unread in inbox (phone banner vs Gmail).
    Does NOT ack WorkPass Lohn.
    """
    from .schema import _ensure_accounting_message_banner_column

    ensure_accounting_schema(db)
    _ensure_accounting_message_banner_column(db)
    row = db.execute("SELECT * FROM accounting_messages WHERE id = ?", (message_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "not_found"}
    if company_id and str(row["company_id"]) != str(company_id):
        return {"ok": False, "error": "forbidden_company"}
    if str(row["status"] or "") != "pending":
        return {"ok": True, "id": message_id, "status": row["status"], "bannerVisible": False}
    now = _now()
    updated = False
    try:
        db.execute(
            """
            UPDATE accounting_messages
            SET banner_dismissed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, message_id),
        )
        updated = True
    except Exception:
        updated = False
    if not updated:
        # Fallback when column migrate failed: store flag inside payload_json
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload["bannerDismissed"] = True
        payload["bannerDismissedAt"] = now
        db.execute(
            """
            UPDATE accounting_messages
            SET payload_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(payload, ensure_ascii=False), now, message_id),
        )
        updated = True
    try:
        db.commit()
    except Exception:
        pass
    return {
        "ok": True,
        "id": message_id,
        "status": "pending",
        "bannerVisible": False,
        "unread": True,
        "acked": False,
        "note": "banner_dismissed_inbox_unread",
        "actorUserId": str(actor_user_id or "")[:80],
    }


def _lohn_get_json(link: dict[str, Any], *, path: str, company_id: str = "") -> dict[str, Any]:
    base = str(link.get("base_url") or "").rstrip("/")
    master = _master_key(link)
    if not base:
        return {"ok": False, "error": "lohn_base_url_missing"}
    if not master:
        return {"ok": False, "error": "master_api_key_missing"}
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base}{path}"
    ts = str(int(__import__("time").time()))
    headers = {
        "Accept": "application/json",
        "User-Agent": "SUPPIX-WorkPass-Lohn-Bridge/1.0",
        "X-WorkPass-Key": master,
        "Authorization": f"Bearer {master}",
        "X-WorkPass-Master-Key": master,
        "X-WorkPass-Company-Id": company_id,
        "X-Suppix-Timestamp": ts,
        "X-Suppix-Event": "messages.pending",
        "X-Suppix-Product": "WorkPass Lohn",
        "X-Suppix-Signature": sign_payload(master, timestamp=ts, body=b""),
    }
    req = urlrequest.Request(url, headers=headers, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {"raw": raw[:500]}
            return {"ok": True, "status": int(resp.status), "url": url, "body": parsed}
    except urlerror.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read()[:400].decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        return {"ok": False, "status": int(exc.code), "url": url, "error": detail or str(exc)[:200]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "url": url}


def pull_pending_messages_from_lohn(db, *, company_id: str | None = None) -> dict[str, Any]:
    """GET {lohn}/v1/messages/pending and upsert into local inbox."""
    from .company_opt_in import is_workpass_lohn_enabled

    link = get_platform_link(db)
    if not link.get("enabled") or not str(link.get("base_url") or "").strip():
        return {"ok": False, "error": "platform_link_disabled"}
    company_id = (company_id or "").strip() or None
    if company_id and not is_workpass_lohn_enabled(db, company_id):
        return {"ok": False, "error": "workpass_lohn_disabled", "skipped": True}
    path = MESSAGES_PENDING_PATH
    if company_id:
        path = f"{MESSAGES_PENDING_PATH}?{urlparse.urlencode({'companyId': company_id})}"
    fetched = _lohn_get_json(link, path=path, company_id=company_id or "")
    if not fetched.get("ok"):
        return {"ok": False, "pull": fetched, "error": fetched.get("error") or "pull_failed"}
    body = fetched.get("body") or {}
    items = []
    if isinstance(body, dict):
        items = body.get("messages") or body.get("items") or body.get("pending") or []
        if isinstance(body.get("message"), dict):
            items = [body["message"]]
    elif isinstance(body, list):
        items = body
    if not isinstance(items, list):
        items = []
    stored = upsert_accounting_messages(db, items, default_company=company_id or "")
    # Poll-fallback: turn Lohn request messages/events into period handoff requests
    handoffs: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ev = str(item.get("event") or item.get("type") or item.get("kind") or "").strip().lower()
        cid = str(
            item.get("companyId") or item.get("company_id") or company_id or ""
        ).strip()
        per = str(item.get("period") or item.get("month") or "").strip()[:7]
        if not cid or not per:
            continue
        if ev in {
            "payroll.month.requested",
            "employees.list.requested",
            "period_request",
            "payroll_month_requested",
            "employees_list_requested",
            "payroll.requested",
        }:
            try:
                from .service import request_period_handoff

                handoffs.append(
                    request_period_handoff(
                        db,
                        company_id=cid,
                        period=per,
                        source="lohn_poll",
                        note=str(item.get("subject") or item.get("body") or ev)[:500],
                        external_ref=str(item.get("id") or item.get("messageId") or "")[:120],
                        notify_inbox=False,
                    )
                )
            except Exception as exc:
                handoffs.append({"ok": False, "error": str(exc)[:120], "companyId": cid, "period": per})
    return {
        "ok": True,
        "pulled": len(items),
        "path": MESSAGES_PENDING_PATH,
        "store": stored,
        "periodRequests": handoffs,
        "pull": {"status": fetched.get("status"), "url": fetched.get("url")},
    }


def handle_inbound_lohn_webhook(db, *, data: dict[str, Any], company_id: str = "") -> dict[str, Any]:
    """
    WORKPASS_PLATFORM_WEBHOOK_URL handler (also /api/workpass/webhooks/accounting).

    Events:
    - employees.list.requested → queue/create period request; push /v1/employees/import when already confirmed
      or when no period (master sync)
    - payroll.month.requested → create pending period request (human confirms, then push batch)
    - payslip.released → ingest statements for human approval / worker visibility path
    - accounting.message → store + pull pending messages
    """
    from .hours_service import normalize_period
    from .service import (
        ingest_statements,
        push_employees_to_lohn,
        push_payroll_batch_to_lohn,
        request_period_handoff,
    )

    data = data if isinstance(data, dict) else {}
    event = str(data.get("event") or data.get("type") or data.get("action") or "").strip()
    company_id = str(
        company_id
        or data.get("companyId")
        or data.get("company_id")
        or (data.get("company") or {}).get("id")
        or ""
    ).strip()
    period = str(data.get("period") or data.get("month") or "").strip()[:7]
    if period:
        try:
            period = normalize_period(period)
        except ValueError:
            period = str(data.get("period") or data.get("month") or "").strip()[:7]

    replies: dict[str, Any] = {}

    # ── employees.list.requested ──────────────────────────────────────
    if event in {
        "employees.list.requested",
        "employees.requested",
        "employee.list.requested",
        "employees.list",
    }:
        if period:
            req = request_period_handoff(
                db,
                company_id=company_id,
                period=period,
                source="lohn_webhook",
                note=str(data.get("note") or data.get("message") or "employees.list.requested")[:500],
                external_ref=str(data.get("id") or data.get("requestId") or data.get("externalRef") or "")[:120],
            )
            replies["periodRequest"] = req
            if req.get("alreadyReleased"):
                replies["employeesImport"] = push_employees_to_lohn(db, company_id=company_id)
                replies["payrollBatch"] = push_payroll_batch_to_lohn(
                    db, company_id=company_id, period=period
                )
        elif company_id:
            # Master sync without month — push immediately
            replies["employeesImport"] = push_employees_to_lohn(db, company_id=company_id)
        messages = [data] if data.get("subject") or data.get("body") or data.get("id") else []
        store = upsert_accounting_messages(db, messages, default_company=company_id) if messages else {
            "ok": True,
            "createdCount": 0,
            "updatedCount": 0,
            "ids": [],
        }
        return {
            "ok": True,
            "event": event,
            "companyId": company_id or None,
            "period": period or None,
            "status": (replies.get("periodRequest") or {}).get("status")
            or ("delivered" if replies.get("employeesImport", {}).get("ok") else "accepted"),
            "replies": replies,
            "webhookStore": store,
            "message": (
                "Period request queued — confirm in Ops to hand off"
                if (replies.get("periodRequest") or {}).get("status") == "pending_confirmation"
                else "Employees reply processed"
            ),
        }

    # ── payroll.month.requested ───────────────────────────────────────
    if event in {
        "payroll.month.requested",
        "payroll.requested",
        "payroll.batch.requested",
        "hours.requested",
        "abrechnung.requested",
    }:
        if not company_id:
            return {"ok": False, "error": "company_id_required", "event": event} 
        if not period:
            from .monthly_job import previous_period

            period = previous_period()
        req = request_period_handoff(
            db,
            company_id=company_id,
            period=period,
            source="lohn_webhook",
            note=str(data.get("note") or data.get("message") or "payroll.month.requested")[:500],
            external_ref=str(data.get("id") or data.get("requestId") or data.get("externalRef") or "")[:120],
        )
        replies["periodRequest"] = req
        if req.get("alreadyReleased"):
            replies["employeesImport"] = push_employees_to_lohn(db, company_id=company_id)
            replies["payrollBatch"] = push_payroll_batch_to_lohn(
                db, company_id=company_id, period=period
            )
        # Always store as inbox message for Ops visibility
        store = upsert_accounting_messages(
            db,
            [
                {
                    **data,
                    "event": EVENT_ACCOUNTING_MESSAGE,
                    "kind": "period_request",
                    "subject": data.get("subject")
                    or f"Lohn-Anfrage: Mitarbeiter & Abrechnung {period}",
                    "body": data.get("body")
                    or (
                        f"WorkPass Lohn möchte Periode {period}. "
                        "Bitte Bestätigen & übergeben im Ops Center."
                    ),
                    "companyId": company_id,
                    "period": period,
                    "id": data.get("id") or data.get("requestId") or f"period-{company_id}-{period}",
                }
            ],
            default_company=company_id,
        )
        return {
            "ok": True,
            "event": event,
            "companyId": company_id,
            "period": period,
            "status": req.get("status"),
            "replies": replies,
            "webhookStore": store,
            "message": req.get("message")
            or "Period request accepted — waiting for platform confirmation",
        }

    # ── payslip.released ──────────────────────────────────────────────
    if event in {"payslip.released", "payslips.released", "statement.released", "statements.released"}:
        statements = data.get("statements") or data.get("items") or data.get("payslips") or []
        if isinstance(data.get("statement"), dict):
            statements = [data["statement"]]
        ingest_result: dict[str, Any] = {"skipped": "no_statements"}
        if company_id and isinstance(statements, list) and statements:
            if not period:
                period = str((statements[0] or {}).get("period") or "").strip()[:7]
            try:
                if period:
                    normalize_period(period)
                ingest_result = ingest_statements(
                    db,
                    company_id=company_id,
                    period=period or previous_period_safe(),
                    statements=statements,
                    external_ref=str(data.get("externalRef") or data.get("id") or ""),
                    notes=str(data.get("notes") or "payslip.released webhook"),
                )
            except Exception as exc:
                ingest_result = {"ok": False, "error": str(exc)[:200]}
        store = upsert_accounting_messages(
            db,
            [
                {
                    **data,
                    "event": EVENT_ACCOUNTING_MESSAGE,
                    "kind": "payslip_released",
                    "subject": data.get("subject") or f"Lohnabrechnung bereit {period or ''}".strip(),
                    "body": data.get("body")
                    or "Lohnabrechnung eingegangen — Freigabe auf der Plattform prüfen (kein Auto-Approve).",
                    "companyId": company_id,
                    "period": period,
                    "id": data.get("id") or data.get("externalRef") or f"payslip-{company_id}-{period}",
                }
            ],
            default_company=company_id,
        ) if company_id else {"ok": True, "createdCount": 0, "updatedCount": 0, "ids": []}
        return {
            "ok": True,
            "event": event,
            "companyId": company_id or None,
            "period": period or None,
            "ingest": ingest_result,
            "webhookStore": store,
            "message": "Payslips ingested as pending_approval — human approve to show worker",
            "note": "Never auto-approve payslips to employees",
        }

    # ── default: accounting.message inbox ─────────────────────────────
    if not event:
        event = EVENT_ACCOUNTING_MESSAGE

    messages: list[dict[str, Any]] = []
    if isinstance(data.get("messages"), list):
        messages = data["messages"]
    elif isinstance(data.get("message"), dict):
        messages = [data["message"]]
    elif event == EVENT_ACCOUNTING_MESSAGE or data.get("subject") or data.get("body") or data.get("id"):
        messages = [data]

    # Convert known request kinds embedded in messages into period requests
    for msg in messages:
        kind = str((msg or {}).get("kind") or (msg or {}).get("event") or "").strip().lower()
        msg_company = str(
            (msg or {}).get("companyId")
            or (msg or {}).get("company_id")
            or company_id
            or ""
        ).strip()
        msg_period = str((msg or {}).get("period") or period or "").strip()[:7]
        if msg_company and msg_period and kind in {
            "period_request",
            "payroll.month.requested",
            "employees.list.requested",
            "payroll_month_requested",
            "employees_list_requested",
        }:
            try:
                replies.setdefault("fromMessages", [])
                replies["fromMessages"].append(
                    request_period_handoff(
                        db,
                        company_id=msg_company,
                        period=msg_period,
                        source="lohn_message",
                        note=str((msg or {}).get("subject") or (msg or {}).get("body") or "")[:500],
                        external_ref=str((msg or {}).get("id") or "")[:120],
                        notify_inbox=False,
                    )
                )
            except Exception as exc:
                replies.setdefault("fromMessages", []).append({"ok": False, "error": str(exc)[:120]})

    store = {"ok": True, "createdCount": 0, "updatedCount": 0, "ids": []}
    if messages:
        store = upsert_accounting_messages(db, messages, default_company=company_id)

    pull: dict[str, Any] = {"skipped": "no_company"}
    if company_id:
        pull = pull_pending_messages_from_lohn(db, company_id=company_id)
    elif event in {EVENT_ACCOUNTING_MESSAGE, "messages.pending", "message.created"}:
        pull = pull_pending_messages_from_lohn(db, company_id=None)

    return {
        "ok": True,
        "event": event,
        "companyId": company_id or None,
        "webhookStore": store,
        "pull": pull,
        "replies": replies,
    }


def previous_period_safe() -> str:
    from .monthly_job import previous_period

    return previous_period()


def platform_webhook_public_path() -> str:
    """Canonical path for WORKPASS_PLATFORM_WEBHOOK_URL on this platform."""
    return "/api/workpass/webhooks/accounting"


def ack_message_to_lohn(
    db,
    *,
    message_id: str,
    actor_user_id: str = "",
    company_id: str | None = None,
    fulfill: bool = True,
) -> dict[str, Any]:
    """Mark message read locally and POST ack to WorkPass Lohn /v1/messages/ack."""
    from .platform_link import _post_lohn_json

    ensure_accounting_schema(db)
    mid = str(message_id or "").strip()
    if not mid:
        return {"ok": False, "error": "not_found"}
    row = db.execute("SELECT * FROM accounting_messages WHERE id = ?", (mid,)).fetchone()
    if not row:
        # UI / Lohn may pass external message id
        row = db.execute(
            "SELECT * FROM accounting_messages WHERE external_id = ?", (mid,)
        ).fetchone()
    if not row:
        return {"ok": False, "error": "not_found"}
    if company_id and str(row["company_id"]) != str(company_id):
        return {"ok": False, "error": "forbidden_company"}

    local_id = str(row["id"])
    if str(row["status"] or "") == "acked":
        return {
            "ok": True,
            "id": local_id,
            "externalId": str(row["external_id"] or ""),
            "status": "acked",
            "alreadyAcked": True,
        }

    now = _now()
    # Local ack first so Ops inbox clears even if Lohn is slow/unreachable.
    db.execute(
        """
        UPDATE accounting_messages
        SET status = 'acked',
            read_at = COALESCE(read_at, ?),
            acked_at = ?,
            ack_error = '',
            updated_at = ?
        WHERE id = ?
        """,
        (now, now, now, local_id),
    )
    try:
        db.commit()
    except Exception:
        pass

    alerts = dismiss_related_data_alerts_for_message(
        db,
        company_id=str(row["company_id"] or ""),
        worker_id=str(row["worker_id"] or ""),
        period=str(row["period"] or ""),
        actor_user_id=str(actor_user_id or ""),
    )

    link = get_platform_link(db)
    external_id = str(row["external_id"] or "")
    company_for_lohn = str(row["company_id"] or "")
    body = {
        "messageId": external_id,
        "id": external_id,
        "companyId": company_for_lohn,
        "event": EVENT_ACCOUNTING_MESSAGE,
        "ackedAt": now,
        "ackedBy": str(actor_user_id or "")[:80],
    }
    ack_remote: dict[str, Any]
    if link.get("enabled") and str(link.get("base_url") or "").strip() and external_id:
        # Short timeout: local inbox already cleared; remote ack is best-effort.
        ack_remote = _post_lohn_json(
            link,
            path=MESSAGES_ACK_PATH,
            body=body,
            event="messages.ack",
            timeout=8,
        )
        if not ack_remote.get("ok") and int(ack_remote.get("status") or 0) == 404:
            ack_remote = _post_lohn_json(
                link,
                path=f"/v1/messages/{urlparse.quote(external_id)}/ack",
                body=body,
                event="messages.ack",
                timeout=8,
            )
    else:
        ack_remote = {"skipped": "platform_link_or_external_id_missing"}

    err = ""
    if not ack_remote.get("ok") and not ack_remote.get("skipped"):
        err = str(ack_remote.get("error") or ack_remote.get("status") or "ack_failed")[:200]
        db.execute(
            """
            UPDATE accounting_messages
            SET ack_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (err, now, local_id),
        )
        try:
            db.commit()
        except Exception:
            pass

    result: dict[str, Any] = {
        "ok": True,
        "id": local_id,
        "externalId": external_id,
        "status": "acked",
        "ack": ack_remote,
        "dataAlerts": alerts,
    }
    if err:
        result["ackWarning"] = err

    # Missing-data requests: push current employee stammdaten back to Lohn when available.
    kind = str(row["kind"] or "").strip().lower()
    raw_worker = str(row["worker_id"] or "").strip()
    if fulfill and kind in _MISSING_DATA_KINDS and company_for_lohn and raw_worker:
        try:
            from .service import notify_employee_data_resolved

            resolved = resolve_company_worker(db, company_for_lohn, raw_worker)
            wid = (resolved or {}).get("id") or raw_worker
            result["fulfill"] = notify_employee_data_resolved(
                db,
                company_id=company_for_lohn,
                worker_id=wid,
                actor_user_id=str(actor_user_id or ""),
                source="message_ack",
            )
        except Exception as exc:
            result["fulfill"] = {"ok": False, "error": str(exc)[:200]}

    if err:
        result["warning"] = "ack_remote_failed"
    elif ack_remote.get("skipped"):
        result["warning"] = "acked_locally_only"
    return result


def create_test_accounting_message(
    db,
    *,
    company_id: str,
    subject: str = "",
    body: str = "",
    period: str = "",
    worker_id: str = "",
    kind: str = "missing_data",
) -> dict[str, Any]:
    """
    Superadmin live-test helper: inject an accounting.message like Lohn would.
    Does not call WorkPass Lohn — verifies toast → banner dismiss → inbox → open/ack UI.
    """
    company_id = (company_id or "").strip()
    if not company_id:
        return {"ok": False, "error": "company_id_required"}
    now = _now()
    external_id = f"test-{uuid.uuid4().hex[:12]}"
    subject = (subject or "Test: Fehlende Mitarbeiterdaten").strip()[:300]
    body = (
        body
        or "Dies ist eine Testnachricht von der Plattform (simuliert WorkPass Lohn). "
        "Mitteilung wegwischen = Banner weg, Posteingang bleibt ungelesen. "
        "Öffnen & bestätigen = Ack."
    ).strip()[:4000]
    period = (period or "").strip()[:7]
    worker_id = (worker_id or "").strip()
    if not worker_id:
        try:
            row = db.execute(
                """
                SELECT id FROM workers
                WHERE company_id = ?
                  AND deleted_at IS NULL
                LIMIT 1
                """,
                (company_id,),
            ).fetchone()
            if row:
                worker_id = str(row["id"] or "").strip()
        except Exception:
            worker_id = ""
    missing_fields = ["taxId", "iban"] if (kind or "").startswith("missing") else []
    stored = upsert_accounting_messages(
        db,
        [
            {
                "id": external_id,
                "messageId": external_id,
                "companyId": company_id,
                "event": EVENT_ACCOUNTING_MESSAGE,
                "kind": kind or "missing_data",
                "subject": subject,
                "body": body,
                "period": period,
                "workerId": worker_id,
                "employeeId": worker_id,
                "missingFields": missing_fields,
                "test": True,
                "createdAt": now,
            }
        ],
        default_company=company_id,
    )
    pending = list_pending_accounting_messages(db, company_id=company_id, limit=20)
    match = next((m for m in pending if m.get("externalId") == external_id), pending[0] if pending else None)
    return {
        "ok": True,
        "test": True,
        "externalId": external_id,
        "companyId": company_id,
        "message": match,
        "store": stored,
        "checklist": [
            "Gelbe Mitteilung oben sichtbar",
            "Mitteilung weg → Banner weg, Posteingang ungelesen",
            "Öffnen & bestätigen → Nachricht verschwindet",
        ],
    }
