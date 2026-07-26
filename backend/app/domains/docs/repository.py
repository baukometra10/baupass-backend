"""WorkPass integrated document editor — repository."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return dict(row)


class EditorDocsRepository:
    def ensure_schema(self, db) -> None:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS editor_documents (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                title TEXT NOT NULL DEFAULT 'Unbenannt',
                mode TEXT NOT NULL DEFAULT 'general',
                status TEXT NOT NULL DEFAULT 'draft',
                content_json TEXT NOT NULL DEFAULT '',
                content_html TEXT NOT NULL DEFAULT '',
                content_text TEXT NOT NULL DEFAULT '',
                worker_id TEXT,
                contract_id TEXT,
                created_by_user_id TEXT,
                updated_by_user_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_editor_documents_company ON editor_documents(company_id, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_editor_documents_mode ON editor_documents(company_id, mode, updated_at DESC)",
        ):
            try:
                db.execute(stmt)
            except Exception:
                pass
        try:
            db.commit()
        except Exception:
            pass

    def list_documents(
        self,
        db,
        *,
        company_id: str | None,
        mode: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.ensure_schema(db)
        limit = max(1, min(int(limit or 50), 200))
        params: list[Any] = []
        where = ["1=1"]
        if company_id:
            where.append("company_id = ?")
            params.append(company_id)
        if mode:
            where.append("mode = ?")
            params.append(mode)
        params.append(limit)
        rows = db.execute(
            f"""
            SELECT id, company_id, title, mode, status, worker_id, contract_id,
                   created_by_user_id, updated_by_user_id, created_at, updated_at,
                   LENGTH(content_text) AS text_len
            FROM editor_documents
            WHERE {' AND '.join(where)}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_document(self, db, doc_id: str, company_id: str | None = None) -> dict[str, Any] | None:
        self.ensure_schema(db)
        if company_id:
            row = db.execute(
                "SELECT * FROM editor_documents WHERE id = ? AND company_id = ?",
                (doc_id, company_id),
            ).fetchone()
        else:
            row = db.execute("SELECT * FROM editor_documents WHERE id = ?", (doc_id,)).fetchone()
        return _row_to_dict(row) if row else None

    def create_document(
        self,
        db,
        *,
        company_id: str | None,
        title: str,
        mode: str,
        content_json: str,
        content_html: str,
        content_text: str,
        worker_id: str | None,
        contract_id: str | None,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        self.ensure_schema(db)
        now = _now()
        doc_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO editor_documents (
                id, company_id, title, mode, status,
                content_json, content_html, content_text,
                worker_id, contract_id,
                created_by_user_id, updated_by_user_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                company_id or None,
                (title or "Unbenannt").strip() or "Unbenannt",
                (mode or "general").strip() or "general",
                content_json or "",
                content_html or "",
                content_text or "",
                worker_id or None,
                contract_id or None,
                actor_user_id or None,
                actor_user_id or None,
                now,
                now,
            ),
        )
        db.commit()
        return self.get_document(db, doc_id) or {"id": doc_id}

    def update_document(
        self,
        db,
        doc_id: str,
        *,
        company_id: str | None,
        title: str | None = None,
        mode: str | None = None,
        status: str | None = None,
        content_json: str | None = None,
        content_html: str | None = None,
        content_text: str | None = None,
        worker_id: str | None = None,
        contract_id: str | None = None,
        actor_user_id: str | None = None,
        clear_worker: bool = False,
        clear_contract: bool = False,
    ) -> dict[str, Any] | None:
        self.ensure_schema(db)
        existing = self.get_document(db, doc_id, company_id=company_id)
        if not existing:
            return None
        sets = ["updated_at = ?", "updated_by_user_id = ?"]
        params: list[Any] = [_now(), actor_user_id or None]
        if title is not None:
            sets.append("title = ?")
            params.append((title or "Unbenannt").strip() or "Unbenannt")
        if mode is not None:
            sets.append("mode = ?")
            params.append((mode or "general").strip() or "general")
        if status is not None:
            sets.append("status = ?")
            params.append((status or "draft").strip() or "draft")
        if content_json is not None:
            sets.append("content_json = ?")
            params.append(content_json)
        if content_html is not None:
            sets.append("content_html = ?")
            params.append(content_html)
        if content_text is not None:
            sets.append("content_text = ?")
            params.append(content_text)
        if clear_worker:
            sets.append("worker_id = NULL")
        elif worker_id is not None:
            sets.append("worker_id = ?")
            params.append(worker_id or None)
        if clear_contract:
            sets.append("contract_id = NULL")
        elif contract_id is not None:
            sets.append("contract_id = ?")
            params.append(contract_id or None)
        params.append(doc_id)
        if company_id:
            db.execute(
                f"UPDATE editor_documents SET {', '.join(sets)} WHERE id = ? AND company_id = ?",
                tuple(params + [company_id]),
            )
        else:
            db.execute(
                f"UPDATE editor_documents SET {', '.join(sets)} WHERE id = ?",
                tuple(params),
            )
        db.commit()
        return self.get_document(db, doc_id, company_id=company_id)

    def delete_document(self, db, doc_id: str, company_id: str | None) -> bool:
        self.ensure_schema(db)
        if company_id:
            cur = db.execute(
                "DELETE FROM editor_documents WHERE id = ? AND company_id = ?",
                (doc_id, company_id),
            )
        else:
            cur = db.execute("DELETE FROM editor_documents WHERE id = ?", (doc_id,))
        db.commit()
        return int(getattr(cur, "rowcount", 0) or 0) > 0

    def find_by_contract(self, db, company_id: str, contract_id: str) -> dict[str, Any] | None:
        self.ensure_schema(db)
        row = db.execute(
            """
            SELECT * FROM editor_documents
            WHERE company_id = ? AND contract_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (company_id, contract_id),
        ).fetchone()
        return _row_to_dict(row) if row else None

    def ensure_versions_schema(self, db) -> None:
        self.ensure_schema(db)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS editor_document_versions (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                company_id TEXT,
                version_no INTEGER NOT NULL DEFAULT 1,
                title TEXT NOT NULL DEFAULT '',
                content_json TEXT NOT NULL DEFAULT '',
                content_html TEXT NOT NULL DEFAULT '',
                content_text TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_by_user_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        try:
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_editor_doc_versions_doc ON editor_document_versions(document_id, version_no DESC)"
            )
        except Exception:
            pass
        try:
            db.commit()
        except Exception:
            pass

    def next_version_no(self, db, document_id: str) -> int:
        self.ensure_versions_schema(db)
        row = db.execute(
            "SELECT COALESCE(MAX(version_no), 0) AS m FROM editor_document_versions WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        return int((row["m"] if row else 0) or 0) + 1

    def add_version(
        self,
        db,
        *,
        document_id: str,
        company_id: str | None,
        title: str,
        content_json: str,
        content_html: str,
        content_text: str,
        note: str,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        self.ensure_versions_schema(db)
        version_no = self.next_version_no(db, document_id)
        vid = str(uuid.uuid4())
        now = _now()
        db.execute(
            """
            INSERT INTO editor_document_versions (
                id, document_id, company_id, version_no, title,
                content_json, content_html, content_text, note,
                created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                vid,
                document_id,
                company_id,
                version_no,
                title or "",
                content_json or "",
                content_html or "",
                content_text or "",
                note or "",
                actor_user_id,
                now,
            ),
        )
        db.commit()
        return {
            "id": vid,
            "document_id": document_id,
            "version_no": version_no,
            "title": title,
            "created_at": now,
            "note": note or "",
        }

    def list_versions(self, db, document_id: str, company_id: str | None, limit: int = 30) -> list[dict[str, Any]]:
        self.ensure_versions_schema(db)
        limit = max(1, min(int(limit or 30), 100))
        if company_id:
            rows = db.execute(
                """
                SELECT id, document_id, company_id, version_no, title, note,
                       created_by_user_id, created_at, LENGTH(content_text) AS text_len
                FROM editor_document_versions
                WHERE document_id = ? AND company_id = ?
                ORDER BY version_no DESC
                LIMIT ?
                """,
                (document_id, company_id, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT id, document_id, company_id, version_no, title, note,
                       created_by_user_id, created_at, LENGTH(content_text) AS text_len
                FROM editor_document_versions
                WHERE document_id = ?
                ORDER BY version_no DESC
                LIMIT ?
                """,
                (document_id, limit),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_version(self, db, version_id: str, company_id: str | None = None) -> dict[str, Any] | None:
        self.ensure_versions_schema(db)
        if company_id:
            row = db.execute(
                "SELECT * FROM editor_document_versions WHERE id = ? AND company_id = ?",
                (version_id, company_id),
            ).fetchone()
        else:
            row = db.execute(
                "SELECT * FROM editor_document_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    def ensure_shares_schema(self, db) -> None:
        self.ensure_schema(db)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS editor_doc_shares (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                company_id TEXT,
                token TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                require_approved INTEGER NOT NULL DEFAULT 0,
                created_by_user_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        try:
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_editor_doc_shares_doc ON editor_doc_shares(document_id, created_at DESC)"
            )
        except Exception:
            pass
        try:
            db.commit()
        except Exception:
            pass

    def create_share(
        self,
        db,
        *,
        document_id: str,
        company_id: str | None,
        token: str,
        password_hash: str | None,
        expires_at: str,
        require_approved: bool,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        self.ensure_shares_schema(db)
        sid = str(uuid.uuid4())
        now = _now()
        db.execute(
            """
            INSERT INTO editor_doc_shares (
                id, document_id, company_id, token, password_hash, expires_at,
                revoked_at, require_approved, created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                sid,
                document_id,
                company_id,
                token,
                password_hash or None,
                expires_at,
                1 if require_approved else 0,
                actor_user_id,
                now,
            ),
        )
        db.commit()
        return self.get_share_by_token(db, token) or {"id": sid, "token": token}

    def get_share_by_token(self, db, token: str) -> dict[str, Any] | None:
        self.ensure_shares_schema(db)
        row = db.execute(
            "SELECT * FROM editor_doc_shares WHERE token = ?",
            (token,),
        ).fetchone()
        return _row_to_dict(row) if row else None

    def revoke_share(self, db, *, document_id: str, company_id: str | None, token: str | None = None) -> int:
        self.ensure_shares_schema(db)
        now = _now()
        if token:
            if company_id:
                cur = db.execute(
                    """
                    UPDATE editor_doc_shares SET revoked_at = ?
                    WHERE document_id = ? AND company_id = ? AND token = ? AND revoked_at IS NULL
                    """,
                    (now, document_id, company_id, token),
                )
            else:
                cur = db.execute(
                    """
                    UPDATE editor_doc_shares SET revoked_at = ?
                    WHERE document_id = ? AND token = ? AND revoked_at IS NULL
                    """,
                    (now, document_id, token),
                )
        else:
            if company_id:
                cur = db.execute(
                    """
                    UPDATE editor_doc_shares SET revoked_at = ?
                    WHERE document_id = ? AND company_id = ? AND revoked_at IS NULL
                    """,
                    (now, document_id, company_id),
                )
            else:
                cur = db.execute(
                    """
                    UPDATE editor_doc_shares SET revoked_at = ?
                    WHERE document_id = ? AND revoked_at IS NULL
                    """,
                    (now, document_id),
                )
        db.commit()
        return int(getattr(cur, "rowcount", 0) or 0)

    def list_shares(self, db, document_id: str, company_id: str | None) -> list[dict[str, Any]]:
        self.ensure_shares_schema(db)
        if company_id:
            rows = db.execute(
                """
                SELECT id, document_id, company_id, expires_at, revoked_at, require_approved,
                       created_at, CASE WHEN password_hash IS NOT NULL AND password_hash != '' THEN 1 ELSE 0 END AS has_password
                FROM editor_doc_shares
                WHERE document_id = ? AND company_id = ?
                ORDER BY created_at DESC LIMIT 40
                """,
                (document_id, company_id),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT id, document_id, company_id, expires_at, revoked_at, require_approved,
                       created_at, CASE WHEN password_hash IS NOT NULL AND password_hash != '' THEN 1 ELSE 0 END AS has_password
                FROM editor_doc_shares
                WHERE document_id = ?
                ORDER BY created_at DESC LIMIT 40
                """,
                (document_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def ensure_templates_schema(self, db) -> None:
        self.ensure_schema(db)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS editor_templates (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT 'Vorlage',
                blurb TEXT NOT NULL DEFAULT '',
                content_html TEXT NOT NULL DEFAULT '',
                layout_json TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'sonstiges',
                created_by_user_id TEXT,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        try:
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_editor_templates_company ON editor_templates(company_id, updated_at DESC)"
            )
        except Exception:
            pass
        try:
            db.execute("ALTER TABLE editor_templates ADD COLUMN category TEXT NOT NULL DEFAULT 'sonstiges'")
        except Exception:
            pass
        try:
            db.commit()
        except Exception:
            pass

    def list_templates(self, db, company_id: str, limit: int = 80) -> list[dict[str, Any]]:
        self.ensure_templates_schema(db)
        limit = max(1, min(int(limit or 80), 200))
        try:
            rows = db.execute(
                """
                SELECT id, company_id, title, blurb, category, created_by_user_id, updated_at, created_at,
                       LENGTH(content_html) AS html_len
                FROM editor_templates
                WHERE company_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (company_id, limit),
            ).fetchall()
        except Exception:
            rows = db.execute(
                """
                SELECT id, company_id, title, blurb, created_by_user_id, updated_at, created_at,
                       LENGTH(content_html) AS html_len
                FROM editor_templates
                WHERE company_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (company_id, limit),
            ).fetchall()
        items = [_row_to_dict(r) for r in rows]
        for it in items:
            if not it.get("category"):
                it["category"] = "sonstiges"
        return items

    def get_template(self, db, template_id: str, company_id: str) -> dict[str, Any] | None:
        self.ensure_templates_schema(db)
        row = db.execute(
            "SELECT * FROM editor_templates WHERE id = ? AND company_id = ?",
            (template_id, company_id),
        ).fetchone()
        return _row_to_dict(row) if row else None

    def create_template(
        self,
        db,
        *,
        company_id: str,
        title: str,
        blurb: str,
        content_html: str,
        layout_json: str,
        actor_user_id: str | None,
        category: str = "sonstiges",
    ) -> dict[str, Any]:
        self.ensure_templates_schema(db)
        tid = str(uuid.uuid4())
        now = _now()
        cat = (category or "sonstiges").strip().lower()[:40] or "sonstiges"
        try:
            db.execute(
                """
                INSERT INTO editor_templates (
                    id, company_id, title, blurb, content_html, layout_json, category,
                    created_by_user_id, updated_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tid,
                    company_id,
                    (title or "Vorlage").strip() or "Vorlage",
                    blurb or "",
                    content_html or "",
                    layout_json or "",
                    cat,
                    actor_user_id,
                    now,
                    now,
                ),
            )
        except Exception:
            db.execute(
                """
                INSERT INTO editor_templates (
                    id, company_id, title, blurb, content_html, layout_json,
                    created_by_user_id, updated_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tid,
                    company_id,
                    (title or "Vorlage").strip() or "Vorlage",
                    blurb or "",
                    content_html or "",
                    layout_json or "",
                    actor_user_id,
                    now,
                    now,
                ),
            )
        db.commit()
        return self.get_template(db, tid, company_id) or {"id": tid, "category": cat}

    def delete_template(self, db, template_id: str, company_id: str) -> bool:
        self.ensure_templates_schema(db)
        cur = db.execute(
            "DELETE FROM editor_templates WHERE id = ? AND company_id = ?",
            (template_id, company_id),
        )
        db.commit()
        return int(getattr(cur, "rowcount", 0) or 0) > 0

    def ensure_presence_schema(self, db) -> None:
        self.ensure_schema(db)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS editor_doc_presence (
                document_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                last_seen TEXT NOT NULL,
                live_html TEXT NOT NULL DEFAULT '',
                live_title TEXT NOT NULL DEFAULT '',
                live_rev INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (document_id, user_id)
            )
            """
        )
        for stmt in (
            "ALTER TABLE editor_doc_presence ADD COLUMN live_html TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE editor_doc_presence ADD COLUMN live_title TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE editor_doc_presence ADD COLUMN live_rev INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE editor_doc_presence ADD COLUMN cursor_index INTEGER NOT NULL DEFAULT -1",
            "ALTER TABLE editor_doc_presence ADD COLUMN cursor_length INTEGER NOT NULL DEFAULT 0",
        ):
            try:
                db.execute(stmt)
            except Exception:
                pass
        try:
            db.commit()
        except Exception:
            pass

    def upsert_presence(
        self,
        db,
        *,
        document_id: str,
        company_id: str,
        user_id: str,
        display_name: str,
        live_html: str | None = None,
        live_title: str | None = None,
        live_rev: int | None = None,
        cursor_index: int | None = None,
        cursor_length: int | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_presence_schema(db)
        now = _now()
        name = (display_name or "").strip()[:80]
        has_live = live_rev is not None
        html = (live_html or "")[:250_000] if has_live else ""
        title = (live_title or "").strip()[:200] if has_live else ""
        rev = int(live_rev or 0) if has_live else 0
        c_idx = int(cursor_index) if cursor_index is not None else -1
        c_len = max(0, int(cursor_length or 0)) if cursor_index is not None else 0
        try:
            db.execute(
                """
                INSERT INTO editor_doc_presence (
                    document_id, company_id, user_id, display_name, last_seen,
                    live_html, live_title, live_rev, cursor_index, cursor_length
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id, user_id) DO UPDATE SET
                  display_name = excluded.display_name,
                  last_seen = excluded.last_seen,
                  company_id = excluded.company_id,
                  live_html = CASE WHEN ? THEN excluded.live_html ELSE editor_doc_presence.live_html END,
                  live_title = CASE WHEN ? THEN excluded.live_title ELSE editor_doc_presence.live_title END,
                  live_rev = CASE WHEN ? THEN excluded.live_rev ELSE editor_doc_presence.live_rev END,
                  cursor_index = excluded.cursor_index,
                  cursor_length = excluded.cursor_length
                """,
                (
                    document_id,
                    company_id,
                    user_id,
                    name,
                    now,
                    html,
                    title,
                    rev,
                    c_idx,
                    c_len,
                    1 if has_live else 0,
                    1 if has_live else 0,
                    1 if has_live else 0,
                ),
            )
        except Exception:
            db.execute(
                "DELETE FROM editor_doc_presence WHERE document_id = ? AND user_id = ?",
                (document_id, user_id),
            )
            db.execute(
                """
                INSERT INTO editor_doc_presence (
                    document_id, company_id, user_id, display_name, last_seen,
                    live_html, live_title, live_rev, cursor_index, cursor_length
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (document_id, company_id, user_id, name, now, html, title, rev, c_idx, c_len),
            )
        db.commit()
        return self.list_presence(db, document_id=document_id, company_id=company_id)

    def list_presence(self, db, *, document_id: str, company_id: str) -> list[dict[str, Any]]:
        self.ensure_presence_schema(db)
        rows = db.execute(
            """
            SELECT document_id, company_id, user_id, display_name, last_seen,
                   live_html, live_title, live_rev, cursor_index, cursor_length
            FROM editor_doc_presence
            WHERE document_id = ? AND company_id = ?
            ORDER BY last_seen DESC
            LIMIT 20
            """,
            (document_id, company_id),
        ).fetchall()
        items = [_row_to_dict(r) for r in rows]
        # Keep only recently seen (~2 min) using string compare on ISO timestamps.
        cutoff = datetime.now(timezone.utc).timestamp() - 120
        fresh = []
        for it in items:
            try:
                ts = datetime.fromisoformat(str(it.get("last_seen") or "").replace("Z", "+00:00")).timestamp()
            except Exception:
                continue
            if ts >= cutoff:
                fresh.append(it)
        return fresh

    def delete_template_as(
        self,
        db,
        template_id: str,
        company_id: str,
        *,
        actor_user_id: str | None,
        allow_any: bool = False,
    ) -> tuple[bool, str | None]:
        """Delete template if actor owns it (or allow_any for superadmin)."""
        self.ensure_templates_schema(db)
        row = self.get_template(db, template_id, company_id)
        if not row:
            return False, "not_found"
        owner = str(row.get("created_by_user_id") or "")
        actor = str(actor_user_id or "")
        if not allow_any and owner and actor and owner != actor:
            return False, "forbidden"
        ok = self.delete_template(db, template_id, company_id)
        return ok, None if ok else "not_found"

    def ensure_signatures_schema(self, db) -> None:
        self.ensure_schema(db)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS editor_doc_signatures (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                signer_name TEXT NOT NULL DEFAULT '',
                actor_user_id TEXT,
                stamped INTEGER NOT NULL DEFAULT 0,
                content_hash TEXT NOT NULL DEFAULT '',
                signature_data TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        try:
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_editor_doc_sigs ON editor_doc_signatures(document_id, created_at DESC)"
            )
        except Exception:
            pass
        try:
            db.commit()
        except Exception:
            pass

    def add_signature(
        self,
        db,
        *,
        document_id: str,
        company_id: str,
        signer_name: str,
        actor_user_id: str | None,
        stamped: bool,
        content_hash: str,
        signature_data: str = "",
    ) -> dict[str, Any]:
        self.ensure_signatures_schema(db)
        sid = str(uuid.uuid4())
        now = _now()
        db.execute(
            """
            INSERT INTO editor_doc_signatures (
                id, document_id, company_id, signer_name, actor_user_id,
                stamped, content_hash, signature_data, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                document_id,
                company_id,
                (signer_name or "").strip()[:120],
                actor_user_id,
                1 if stamped else 0,
                (content_hash or "")[:128],
                (signature_data or "")[:120000],
                now,
            ),
        )
        db.commit()
        row = db.execute("SELECT * FROM editor_doc_signatures WHERE id = ?", (sid,)).fetchone()
        return _row_to_dict(row)

    def list_signatures(self, db, *, document_id: str, company_id: str) -> list[dict[str, Any]]:
        self.ensure_signatures_schema(db)
        rows = db.execute(
            """
            SELECT id, document_id, company_id, signer_name, actor_user_id, stamped,
                   content_hash, created_at
            FROM editor_doc_signatures
            WHERE document_id = ? AND company_id = ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (document_id, company_id),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def dumps_json(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""
