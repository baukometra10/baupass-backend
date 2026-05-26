"""
Developer API key management.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

API_KEY_PREFIX = "bp_live_"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def create_api_key(
    db,
    *,
    company_id: int,
    name: str,
    scopes: str,
    created_by_user_id: str | None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    key_id = f"apk-{uuid.uuid4().hex[:12]}"
    raw_key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    prefix = raw_key[:16]
    db.execute(
        """
        INSERT INTO developer_api_keys
            (id, company_id, name, key_prefix, key_hash, scopes, status, created_by_user_id, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """,
        (key_id, company_id, name.strip(), prefix, _hash_key(raw_key), scopes.strip(), created_by_user_id, _now_iso(), expires_at),
    )
    db.commit()
    return {
        "id": key_id,
        "name": name,
        "key_prefix": prefix,
        "api_key": raw_key,
        "scopes": scopes,
        "expires_at": expires_at,
        "warning": "Store api_key now; it will not be shown again.",
    }


def list_api_keys(db, company_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT id, company_id, name, key_prefix, scopes, status, created_at, last_used_at, expires_at
        FROM developer_api_keys
        WHERE company_id = ?
        ORDER BY created_at DESC
        """,
        (company_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def revoke_api_key(db, company_id: int, key_id: str) -> bool:
    cur = db.execute(
        """
        UPDATE developer_api_keys SET status = 'revoked'
        WHERE id = ? AND company_id = ? AND status = 'active'
        """,
        (key_id, company_id),
    )
    db.commit()
    return cur.rowcount > 0


def authenticate_api_key(db, raw_key: str) -> dict[str, Any] | None:
    if not raw_key or not raw_key.startswith(API_KEY_PREFIX):
        return None
    key_hash = _hash_key(raw_key)
    row = db.execute(
        """
        SELECT id, company_id, name, scopes, status, expires_at
        FROM developer_api_keys
        WHERE key_hash = ? AND status = 'active'
        """,
        (key_hash,),
    ).fetchone()
    if not row:
        return None
    if row["expires_at"] and row["expires_at"] < _now_iso():
        return None
    db.execute(
        "UPDATE developer_api_keys SET last_used_at = ? WHERE id = ?",
        (_now_iso(), row["id"]),
    )
    db.commit()
    return dict(row)
