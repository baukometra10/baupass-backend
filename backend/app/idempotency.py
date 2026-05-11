from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_request(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def claim_idempotency_key(
    conn: sqlite3.Connection,
    *,
    scope: str,
    key: str,
    payload: dict[str, Any],
    company_id: Optional[int] = None,
    ttl_seconds: int = 24 * 3600,
) -> dict[str, Any]:
    """
    Claims an idempotency key for an operation.

    Returns:
      - {"status": "claimed"}
      - {"status": "completed", "response": {...}} when duplicate completed request exists
      - {"status": "processing"} when another worker is processing same key
    """
    request_hash = _hash_request(payload or {})
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()

    conn.execute(
        """
        INSERT OR IGNORE INTO idempotency_keys (
            company_id, scope, idempotency_key, status, request_hash, expires_at
        ) VALUES (?, ?, ?, 'processing', ?, ?)
        """,
        (company_id, scope, key, request_hash, expires_at),
    )

    row = conn.execute(
        """
        SELECT status, request_hash, response_json
        FROM idempotency_keys
        WHERE company_id IS ? AND scope = ? AND idempotency_key = ?
        """,
        (company_id, scope, key),
    ).fetchone()

    if not row:
        return {"status": "processing"}

    if row["request_hash"] and row["request_hash"] != request_hash:
        raise ValueError("Idempotency key re-used with a different payload")

    if row["status"] == "completed":
        response = json.loads(row["response_json"]) if row["response_json"] else None
        return {"status": "completed", "response": response}

    if row["status"] == "processing":
        # If insert ignored and already processing by another actor.
        return {"status": "claimed" if conn.total_changes > 0 else "processing"}

    return {"status": "processing"}


def complete_idempotency_key(
    conn: sqlite3.Connection,
    *,
    scope: str,
    key: str,
    response: dict[str, Any],
    company_id: Optional[int] = None,
) -> None:
    conn.execute(
        """
        UPDATE idempotency_keys
        SET status = 'completed',
            response_json = ?,
            completed_at = ?
        WHERE company_id IS ? AND scope = ? AND idempotency_key = ?
        """,
        (json.dumps(response, separators=(",", ":")), _utc_now_iso(), company_id, scope, key),
    )


def fail_idempotency_key(
    conn: sqlite3.Connection,
    *,
    scope: str,
    key: str,
    company_id: Optional[int] = None,
) -> None:
    conn.execute(
        """
        UPDATE idempotency_keys
        SET status = 'failed'
        WHERE company_id IS ? AND scope = ? AND idempotency_key = ?
        """,
        (company_id, scope, key),
    )
