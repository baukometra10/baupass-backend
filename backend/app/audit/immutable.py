from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _resolve_audit_key() -> str:
    key = os.getenv("BAUPASS_AUDIT_SIGNING_KEY", "").strip()
    if key:
        return key

    # Fallback for non-production environments.
    return os.getenv("BAUPASS_SECRET_KEY", "").strip() or "dev-insecure-audit-key"


def _build_event_hash(
    prev_hash: str,
    event_id: str,
    event_type: str,
    company_id: Optional[int],
    actor_id: Optional[str],
    request_id: Optional[str],
    source: str,
    occurred_at: str,
    payload_json: str,
) -> str:
    content = "|".join(
        [
            prev_hash,
            event_id,
            event_type,
            str(company_id) if company_id is not None else "",
            actor_id or "",
            request_id or "",
            source,
            occurred_at,
            payload_json,
        ]
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _build_signature(event_hash: str, key: str) -> str:
    return hmac.new(key.encode("utf-8"), event_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def append_immutable_audit_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    payload: dict[str, Any],
    company_id: Optional[int] = None,
    actor_id: Optional[str] = None,
    request_id: Optional[str] = None,
    source: str = "api",
    occurred_at: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    key_id: str = "v1",
) -> dict[str, Any]:
    """
    Appends a tamper-evident immutable audit event.

    Returns:
        {"inserted": bool, "event_id": str, "event_hash": str, "signature": str}
    """
    if not event_type.strip():
        raise ValueError("event_type is required")

    occurred_at = occurred_at or _utc_now_iso()
    payload_json = _canonical_json(payload or {})

    if idempotency_key:
        existing = conn.execute(
            "SELECT event_id, event_hash, signature FROM immutable_audit_events WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            return {
                "inserted": False,
                "event_id": existing["event_id"],
                "event_hash": existing["event_hash"],
                "signature": existing["signature"],
            }

    last = conn.execute(
        "SELECT event_hash FROM immutable_audit_events ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    prev_hash = (last["event_hash"] if last else "") or ""

    event_id = secrets.token_hex(16)
    event_hash = _build_event_hash(
        prev_hash=prev_hash,
        event_id=event_id,
        event_type=event_type,
        company_id=company_id,
        actor_id=actor_id,
        request_id=request_id,
        source=source,
        occurred_at=occurred_at,
        payload_json=payload_json,
    )
    signature = _build_signature(event_hash, _resolve_audit_key())

    conn.execute(
        """
        INSERT INTO immutable_audit_events (
            event_id, event_type, company_id, actor_id, request_id,
            source, occurred_at, payload_json, prev_hash, event_hash,
            signature, key_id, idempotency_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            event_type,
            company_id,
            actor_id,
            request_id,
            source,
            occurred_at,
            payload_json,
            prev_hash,
            event_hash,
            signature,
            key_id,
            idempotency_key,
        ),
    )

    return {
        "inserted": True,
        "event_id": event_id,
        "event_hash": event_hash,
        "signature": signature,
    }


def verify_immutable_audit_chain(
    conn: sqlite3.Connection,
    *,
    limit: Optional[int] = None,
    strict_signature: bool = True,
) -> dict[str, Any]:
    """
    Verifies hash chain and signatures.

    Returns:
        {
          "ok": bool,
          "checked": int,
          "last_seq": int | None,
          "error": str | None
        }
    """
    sql = (
        "SELECT seq, event_id, event_type, company_id, actor_id, request_id, source, "
        "occurred_at, payload_json, prev_hash, event_hash, signature "
        "FROM immutable_audit_events ORDER BY seq ASC"
    )
    params: tuple[Any, ...] = ()
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params = (limit,)

    rows = conn.execute(sql, params).fetchall()
    key = _resolve_audit_key()

    prev = ""
    for row in rows:
        if (row["prev_hash"] or "") != prev:
            return {
                "ok": False,
                "checked": int(row["seq"]),
                "last_seq": int(row["seq"]),
                "error": "prev_hash mismatch",
            }

        expected_hash = _build_event_hash(
            prev_hash=prev,
            event_id=row["event_id"],
            event_type=row["event_type"],
            company_id=row["company_id"],
            actor_id=row["actor_id"],
            request_id=row["request_id"],
            source=row["source"],
            occurred_at=row["occurred_at"],
            payload_json=row["payload_json"],
        )
        if row["event_hash"] != expected_hash:
            return {
                "ok": False,
                "checked": int(row["seq"]),
                "last_seq": int(row["seq"]),
                "error": "event_hash mismatch",
            }

        if strict_signature:
            expected_sig = _build_signature(expected_hash, key)
            if row["signature"] != expected_sig:
                return {
                    "ok": False,
                    "checked": int(row["seq"]),
                    "last_seq": int(row["seq"]),
                    "error": "signature mismatch",
                }

        prev = row["event_hash"]

    last_seq = int(rows[-1]["seq"]) if rows else None
    return {"ok": True, "checked": len(rows), "last_seq": last_seq, "error": None}
