"""E2E identity — public keys only. Private keys must never be stored or accepted."""
from __future__ import annotations

import base64
import re
import uuid
from datetime import datetime, timezone
from typing import Any

_FORBIDDEN_KEY_PATTERN = re.compile(
    r"(private[_-]?key|secret[_-]?key|BEGIN\s+(?:RSA\s+)?PRIVATE)",
    re.IGNORECASE,
)
_ALLOWED_ALGORITHMS = frozenset({"X25519"})
_MAX_PUBLIC_KEY_B64_LEN = 4096


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def assert_no_private_key_material(payload: dict[str, Any] | None) -> None:
    """Reject requests that attempt to upload private key bytes."""
    if not isinstance(payload, dict):
        return
    for key, value in payload.items():
        key_text = str(key or "")
        if _FORBIDDEN_KEY_PATTERN.search(key_text):
            raise ValueError("private_key_forbidden")
        if isinstance(value, str) and _FORBIDDEN_KEY_PATTERN.search(value):
            raise ValueError("private_key_forbidden")


def normalize_public_key_spki_b64(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("public_key_required")
    if len(text) > _MAX_PUBLIC_KEY_B64_LEN:
        raise ValueError("public_key_too_large")
    if _FORBIDDEN_KEY_PATTERN.search(text):
        raise ValueError("private_key_forbidden")
    try:
        raw = base64.b64decode(text, validate=True)
    except Exception as exc:
        raise ValueError("public_key_invalid") from exc
    if len(raw) < 32 or len(raw) > 512:
        raise ValueError("public_key_invalid")
    return text


def normalize_algorithm(value: str) -> str:
    alg = str(value or "X25519").strip().upper()
    if alg not in _ALLOWED_ALGORITHMS:
        raise ValueError("algorithm_unsupported")
    return alg


class E2EIdentityService:
    TABLE = "e2e_identity_keys"

    def __init__(self, db):
        self.db = db
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE} (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                company_id TEXT,
                public_key_spki_b64 TEXT NOT NULL,
                algorithm TEXT NOT NULL DEFAULT 'X25519',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(entity_type, entity_id)
            )
            """
        )
        self.db.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_e2e_identity_company
            ON {self.TABLE}(company_id, entity_type)
            """
        )
        try:
            cols = {str(row[1] if isinstance(row, tuple) else row["name"]) for row in self.db.execute(f"PRAGMA table_info({self.TABLE})").fetchall()}
            if "identity_backup_json" not in cols:
                self.db.execute(f"ALTER TABLE {self.TABLE} ADD COLUMN identity_backup_json TEXT")
            self.db.commit()
        except Exception:
            try:
                self.db.commit()
            except Exception:
                pass

    def upsert_identity(
        self,
        *,
        entity_type: str,
        entity_id: str,
        company_id: str | None,
        public_key_spki_b64: str,
        algorithm: str = "X25519",
    ) -> dict[str, Any]:
        etype = str(entity_type or "").strip().lower()
        eid = str(entity_id or "").strip()
        if etype not in {"worker", "user"}:
            raise ValueError("entity_type_invalid")
        if not eid:
            raise ValueError("entity_id_required")
        pub = normalize_public_key_spki_b64(public_key_spki_b64)
        alg = normalize_algorithm(algorithm)
        now = utc_now_iso()
        existing = self.db.execute(
            f"SELECT id FROM {self.TABLE} WHERE entity_type = ? AND entity_id = ?",
            (etype, eid),
        ).fetchone()
        if existing:
            self.db.execute(
                f"""
                UPDATE {self.TABLE}
                SET public_key_spki_b64 = ?, algorithm = ?, company_id = ?, updated_at = ?
                WHERE entity_type = ? AND entity_id = ?
                """,
                (pub, alg, company_id, now, etype, eid),
            )
            row_id = str(existing[0])
        else:
            row_id = f"e2e-{uuid.uuid4().hex[:16]}"
            self.db.execute(
                f"""
                INSERT INTO {self.TABLE}
                (id, entity_type, entity_id, company_id, public_key_spki_b64, algorithm, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row_id, etype, eid, company_id, pub, alg, now, now),
            )
        self.db.commit()
        return self.get_identity(etype, eid) or {}

    def get_identity_backup(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        etype = str(entity_type or "").strip().lower()
        eid = str(entity_id or "").strip()
        if not eid:
            return None
        self._ensure_schema()
        try:
            row = self.db.execute(
                f"SELECT identity_backup_json FROM {self.TABLE} WHERE entity_type = ? AND entity_id = ?",
                (etype, eid),
            ).fetchone()
        except Exception:
            return None
        if not row:
            return None
        raw = str(row[0] if isinstance(row, tuple) else row["identity_backup_json"] or "").strip()
        if not raw:
            return None
        import json

        try:
            parsed = json.loads(raw)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def upsert_identity_backup(self, entity_type: str, entity_id: str, backup: dict[str, Any] | None) -> dict[str, Any] | None:
        etype = str(entity_type or "").strip().lower()
        eid = str(entity_id or "").strip()
        if not eid:
            raise ValueError("entity_id_required")
        if backup is not None:
            assert_no_private_key_material(backup)
            iv = str(backup.get("iv") or "").strip()
            ct = str(backup.get("ct") or "").strip()
            if not iv or not ct:
                raise ValueError("backup_invalid")
            if len(iv) > 256 or len(ct) > 65536:
                raise ValueError("backup_too_large")
        import json

        self._ensure_schema()
        now = utc_now_iso()
        payload = json.dumps(backup, separators=(",", ":")) if backup else ""
        existing = self.db.execute(
            f"SELECT id FROM {self.TABLE} WHERE entity_type = ? AND entity_id = ?",
            (etype, eid),
        ).fetchone()
        if not existing:
            raise ValueError("identity_not_found")
        self.db.execute(
            f"""
            UPDATE {self.TABLE}
            SET identity_backup_json = ?, updated_at = ?
            WHERE entity_type = ? AND entity_id = ?
            """,
            (payload, now, etype, eid),
        )
        self.db.commit()
        return self.get_identity_backup(etype, eid)

    def get_identity(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            f"""
            SELECT id, entity_type, entity_id, company_id, public_key_spki_b64, algorithm, created_at, updated_at
            FROM {self.TABLE}
            WHERE entity_type = ? AND entity_id = ?
            """,
            (str(entity_type).lower(), str(entity_id)),
        ).fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def list_company_chat_keys(self, company_id: str, worker_id: str | None = None) -> list[dict[str, Any]]:
        cid = str(company_id or "").strip()
        if not cid:
            return []
        keys: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        def _add_row(row) -> None:
            item = self._row_to_dict(row)
            row_id = str(item.get("id") or "")
            if row_id and row_id not in seen_ids:
                seen_ids.add(row_id)
                keys.append(item)

        admin_rows = self.db.execute(
            f"""
            SELECT e.id, e.entity_type, e.entity_id, e.company_id, e.public_key_spki_b64, e.algorithm, e.created_at, e.updated_at
            FROM {self.TABLE} e
            INNER JOIN users u ON e.entity_type = 'user' AND e.entity_id = u.id
            WHERE u.company_id = ?
              AND lower(trim(coalesce(u.role, ''))) IN ('company-admin', 'admin', 'manager', 'superadmin')
            """,
            (cid,),
        ).fetchall()
        for row in admin_rows:
            _add_row(row)

        legacy_admin_rows = self.db.execute(
            f"""
            SELECT id, entity_type, entity_id, company_id, public_key_spki_b64, algorithm, created_at, updated_at
            FROM {self.TABLE}
            WHERE entity_type = 'user' AND company_id = ?
            """,
            (cid,),
        ).fetchall()
        for row in legacy_admin_rows:
            _add_row(row)

        if not any(str(k.get("entityType") or "").lower() == "user" for k in keys):
            super_rows = self.db.execute(
                f"""
                SELECT e.id, e.entity_type, e.entity_id, e.company_id, e.public_key_spki_b64, e.algorithm, e.created_at, e.updated_at
                FROM {self.TABLE} e
                INNER JOIN users u ON e.entity_type = 'user' AND e.entity_id = u.id
                WHERE lower(trim(coalesce(u.role, ''))) = 'superadmin'
                LIMIT 5
                """
            ).fetchall()
            for row in super_rows:
                _add_row(row)

        wid = str(worker_id or "").strip()
        if wid:
            worker_row = self.db.execute(
                f"""
                SELECT id, entity_type, entity_id, company_id, public_key_spki_b64, algorithm, created_at, updated_at
                FROM {self.TABLE}
                WHERE entity_type = 'worker' AND entity_id = ?
                ORDER BY CASE WHEN company_id = ? THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (wid, cid),
            ).fetchone()
            if worker_row:
                _add_row(worker_row)
        return keys

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        return {
            "id": str(row[0]),
            "entityType": str(row[1]),
            "entityId": str(row[2]),
            "companyId": str(row[3] or ""),
            "publicKeySpkiB64": str(row[4]),
            "algorithm": str(row[5]),
            "createdAt": str(row[6]),
            "updatedAt": str(row[7]),
        }
