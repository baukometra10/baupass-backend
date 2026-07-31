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
from .platform_link import get_platform_link
from .schema import ensure_accounting_schema

MESSAGES_PENDING_PATH = "/v1/messages/pending"
MESSAGES_ACK_PATH = "/v1/messages/ack"
EVENT_ACCOUNTING_MESSAGE = "accounting.message"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _master_key(link: dict[str, Any] | None = None) -> str:
    link = link or {}
    return str(link.get("master_api_key") or "").strip()


def verify_platform_webhook_auth(
    db,
    *,
    headers: dict[str, str],
    body: bytes,
    company_id: str = "",
) -> dict[str, Any]:
    """
    Auth for WORKPASS_PLATFORM_WEBHOOK_URL inbound posts from Lohn.
    Accepts master key (X-WorkPass-Key) or per-company accounting key.
    """
    from .auth import authenticate_accounting_request

    hdr = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    key = (
        hdr.get("x-workpass-key")
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
    master = _master_key(link)
    ts = (hdr.get("x-suppix-timestamp") or "").strip()
    sig = (hdr.get("x-suppix-signature") or "").strip()

    if master and key and key == master:
        if sig and not verify_signature(master, timestamp=ts, body=body or b"", signature=sig):
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
    ids: list[str] = []
    now = _now()
    for raw in messages or []:
        norm = _normalize_message_item(raw, default_company=default_company)
        if not norm:
            continue
        existing = db.execute(
            """
            SELECT id, status FROM accounting_messages
            WHERE company_id = ? AND external_id = ?
            LIMIT 1
            """,
            (norm["companyId"], norm["externalId"]),
        ).fetchone()
        payload_json = json.dumps(norm["payload"], ensure_ascii=False)
        if existing:
            # Re-open banner for fresh/updated Lohn messages
            try:
                existing_payload = json.loads(
                    (db.execute("SELECT payload_json FROM accounting_messages WHERE id = ?", (existing["id"],)).fetchone() or {})["payload_json"]
                    or "{}"
                )
            except Exception:
                existing_payload = {}
            if isinstance(existing_payload, dict):
                existing_payload.pop("bannerDismissed", None)
                existing_payload.pop("banner_dismissed", None)
                existing_payload.pop("bannerDismissedAt", None)
            merged_payload = {**(existing_payload if isinstance(existing_payload, dict) else {}), **(norm["payload"] if isinstance(norm["payload"], dict) else {})}
            merged_payload.pop("bannerDismissed", None)
            merged_payload.pop("banner_dismissed", None)
            payload_json = json.dumps(merged_payload, ensure_ascii=False)
            try:
                db.execute(
                    """
                    UPDATE accounting_messages
                    SET event = ?, kind = ?, subject = ?, body = ?, period = ?, worker_id = ?,
                        payload_json = ?, status = 'pending', updated_at = ?, ack_error = '',
                        acked_at = NULL, banner_dismissed_at = NULL, received_at = ?
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
                        payload_json = ?, status = 'pending', updated_at = ?, ack_error = '',
                        acked_at = NULL, received_at = ?
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
    return {"ok": True, "createdCount": created, "updatedCount": updated, "ids": ids}


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
        out.append(
            {
                "id": data.get("id"),
                "externalId": data.get("external_id"),
                "companyId": data.get("company_id"),
                "event": data.get("event") or EVENT_ACCOUNTING_MESSAGE,
                "kind": data.get("kind") or "",
                "subject": data.get("subject") or "",
                "body": data.get("body") or "",
                "period": data.get("period") or "",
                "workerId": worker_id,
                "workerFirstName": data.get("first_name") or "",
                "workerLastName": data.get("last_name") or "",
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
    return {
        "ok": True,
        "pulled": len(items),
        "path": MESSAGES_PENDING_PATH,
        "store": stored,
        "pull": {"status": fetched.get("status"), "url": fetched.get("url")},
    }


def handle_inbound_lohn_webhook(db, *, data: dict[str, Any], company_id: str = "") -> dict[str, Any]:
    """
    WORKPASS_PLATFORM_WEBHOOK_URL handler.
    On accounting.message: store payload and/or pull /v1/messages/pending.
    """
    data = data if isinstance(data, dict) else {}
    event = str(data.get("event") or data.get("type") or "").strip() or EVENT_ACCOUNTING_MESSAGE
    company_id = str(
        company_id
        or data.get("companyId")
        or data.get("company_id")
        or (data.get("company") or {}).get("id")
        or ""
    ).strip()

    messages: list[dict[str, Any]] = []
    if isinstance(data.get("messages"), list):
        messages = data["messages"]
    elif isinstance(data.get("message"), dict):
        messages = [data["message"]]
    elif event == EVENT_ACCOUNTING_MESSAGE or data.get("subject") or data.get("body") or data.get("id"):
        messages = [data]

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
    }


def ack_message_to_lohn(
    db,
    *,
    message_id: str,
    actor_user_id: str = "",
    company_id: str | None = None,
) -> dict[str, Any]:
    """Mark message read locally and POST ack to WorkPass Lohn /v1/messages/ack."""
    from .platform_link import _post_lohn_json

    ensure_accounting_schema(db)
    row = db.execute("SELECT * FROM accounting_messages WHERE id = ?", (message_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "not_found"}
    if company_id and str(row["company_id"]) != str(company_id):
        return {"ok": False, "error": "forbidden_company"}
    now = _now()
    db.execute(
        "UPDATE accounting_messages SET read_at = COALESCE(read_at, ?), updated_at = ? WHERE id = ?",
        (now, now, message_id),
    )
    try:
        db.commit()
    except Exception:
        pass

    link = get_platform_link(db)
    external_id = str(row["external_id"] or "")
    body = {
        "messageId": external_id,
        "id": external_id,
        "companyId": row["company_id"],
        "event": EVENT_ACCOUNTING_MESSAGE,
        "ackedAt": now,
        "ackedBy": str(actor_user_id or "")[:80],
    }
    ack_remote: dict[str, Any]
    if link.get("enabled") and str(link.get("base_url") or "").strip() and external_id:
        ack_remote = _post_lohn_json(
            link,
            path=MESSAGES_ACK_PATH,
            body=body,
            event="messages.ack",
        )
        if not ack_remote.get("ok") and int(ack_remote.get("status") or 0) == 404:
            ack_remote = _post_lohn_json(
                link,
                path=f"/v1/messages/{urlparse.quote(external_id)}/ack",
                body=body,
                event="messages.ack",
            )
    else:
        ack_remote = {"skipped": "platform_link_or_external_id_missing"}

    err = ""
    if not ack_remote.get("ok") and not ack_remote.get("skipped"):
        err = str(ack_remote.get("error") or ack_remote.get("status") or "ack_failed")[:200]

    db.execute(
        """
        UPDATE accounting_messages
        SET status = 'acked', acked_at = ?, ack_error = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, err, now, message_id),
    )
    try:
        db.commit()
    except Exception:
        pass
    result: dict[str, Any] = {
        "ok": True,
        "id": message_id,
        "externalId": external_id,
        "status": "acked",
        "ack": ack_remote,
    }
    if err:
        result["warning"] = "ack_remote_failed"
    elif ack_remote.get("skipped"):
        result["warning"] = "acked_locally_only"
    return result


def platform_webhook_public_path() -> str:
    """Canonical path for WORKPASS_PLATFORM_WEBHOOK_URL on this platform."""
    return "/api/v2/accounting/webhook"


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
