from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.platform.events.bus import publish_event
from backend.app.platform.notifications.worker_mitteilung import notify_worker_mitteilung
from backend.app.platform.security.e2e_envelope import assert_e2e_attachment, assert_e2e_message_body, is_e2e_envelope
from backend.app.platform.security.e2e_policy import is_e2e_attachment_required, is_e2e_chat_required
from backend.app.platform.security.field_encryption import maybe_decrypt_field, maybe_encrypt_field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        text = value.isoformat()
        return text.replace("+00:00", "Z") if value.tzinfo else f"{text}Z"
    return value


def _json_safe_row(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        source = row
    elif hasattr(row, "keys"):
        try:
            source = {key: row[key] for key in row.keys()}
        except Exception:
            return {}
    else:
        return {}
    return {str(key): _json_safe_value(value) for key, value in source.items()}


class ChatService:
    def __init__(self, db):
        self.db = db
        self._ensure_schema()

    def _table_columns(self, table: str) -> set[str]:
        try:
            return {
                str(row[1])
                for row in self.db.execute(f"PRAGMA table_info({table})").fetchall()
            }
        except Exception:
            try:
                return {
                    str(row[0])
                    for row in self.db.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                        (table,),
                    ).fetchall()
                }
            except Exception:
                return set()

    def _ensure_schema(self) -> None:
        try:
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_threads (
                    id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    subject TEXT NOT NULL DEFAULT 'general',
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_message_at TEXT,
                    last_worker_read_at TEXT,
                    last_admin_read_at TEXT,
                    created_by_user_id TEXT
                )
                """
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    sender_type TEXT NOT NULL,
                    sender_user_id TEXT,
                    sender_worker_id TEXT,
                    body TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    read_at TEXT
                )
                """
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_attachments (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL DEFAULT '',
                    file_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            thread_cols = self._table_columns("chat_threads")
            for column, ddl in (
                ("last_worker_read_at", "ALTER TABLE chat_threads ADD COLUMN last_worker_read_at TEXT"),
                ("last_admin_read_at", "ALTER TABLE chat_threads ADD COLUMN last_admin_read_at TEXT"),
                ("last_message_at", "ALTER TABLE chat_threads ADD COLUMN last_message_at TEXT"),
                ("created_by_user_id", "ALTER TABLE chat_threads ADD COLUMN created_by_user_id TEXT"),
                ("subject", "ALTER TABLE chat_threads ADD COLUMN subject TEXT NOT NULL DEFAULT 'general'"),
                ("status", "ALTER TABLE chat_threads ADD COLUMN status TEXT NOT NULL DEFAULT 'open'"),
            ):
                if column not in thread_cols:
                    try:
                        self.db.execute(ddl)
                    except Exception:
                        pass
            message_cols = self._table_columns("chat_messages")
            for column, ddl in (
                ("sender_user_id", "ALTER TABLE chat_messages ADD COLUMN sender_user_id TEXT"),
                ("sender_worker_id", "ALTER TABLE chat_messages ADD COLUMN sender_worker_id TEXT"),
                ("read_at", "ALTER TABLE chat_messages ADD COLUMN read_at TEXT"),
                ("body", "ALTER TABLE chat_messages ADD COLUMN body TEXT NOT NULL DEFAULT ''"),
            ):
                if column not in message_cols:
                    try:
                        self.db.execute(ddl)
                    except Exception:
                        pass
            attachment_cols = self._table_columns("chat_attachments")
            if "e2e_meta" not in attachment_cols:
                try:
                    self.db.execute("ALTER TABLE chat_attachments ADD COLUMN e2e_meta TEXT")
                except Exception:
                    pass
            self.db.commit()
        except Exception:
            pass

    def list_threads(self, company_id: str, *, worker_id: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = [company_id]
        where = "t.company_id = ?"
        if worker_id:
            where += " AND t.worker_id = ?"
            params.append(worker_id)
        rows = self.db.execute(
            f"""
            SELECT t.*, w.first_name, w.last_name, w.badge_id
            FROM chat_threads t
            LEFT JOIN workers w ON w.id = t.worker_id
            WHERE {where}
            ORDER BY COALESCE(t.last_message_at, t.updated_at) DESC
            """,
            tuple(params),
        ).fetchall()
        return [_json_safe_row(row) for row in rows]

    def _message_preview_text(self, body: Any, company_id: str) -> str:
        raw = maybe_decrypt_field(body, company_id=company_id) if body else ""
        text = str(raw or "").strip()
        if not text:
            return ""
        if is_e2e_envelope(text):
            return "encrypted"
        return text[:120]

    def _fetch_thread_summaries(self, company_id: str) -> dict[str, dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT
                t.id AS thread_id,
                (
                    SELECT COUNT(*)
                    FROM chat_messages wm
                    WHERE wm.thread_id = t.id
                      AND wm.sender_type = 'worker'
                      AND wm.created_at > COALESCE(NULLIF(t.last_admin_read_at, ''), '1970-01-01T00:00:00Z')
                ) AS unread_count,
                lm.body AS last_body,
                lm.sender_type AS last_sender_type,
                lm.created_at AS last_message_at
            FROM chat_threads t
            LEFT JOIN chat_messages lm ON lm.thread_id = t.id
                AND lm.created_at = (
                    SELECT MAX(m2.created_at)
                    FROM chat_messages m2
                    WHERE m2.thread_id = t.id
                )
            WHERE t.company_id = ?
            """,
            (company_id,),
        ).fetchall()
        summaries: dict[str, dict[str, Any]] = {}
        for row in rows:
            thread_id = str(row["thread_id"] or "")
            if not thread_id:
                continue
            summaries[thread_id] = {
                "last_message_preview": self._message_preview_text(row["last_body"], company_id),
                "last_message_sender_type": str(row["last_sender_type"] or ""),
                "last_message_at": row["last_message_at"],
                "unread_count": int(row["unread_count"] or 0),
            }
        return summaries

    def list_admin_chat_directory(self, company_id: str) -> list[dict[str, Any]]:
        """All active workers for admin chat, with optional existing thread metadata."""
        workers = self.db.execute(
            """
            SELECT id, first_name, last_name, badge_id, status
            FROM workers
            WHERE company_id = ?
              AND deleted_at IS NULL
              AND worker_type = 'worker'
            ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE
            """,
            (company_id,),
        ).fetchall()
        threads = self.list_threads(company_id)
        summaries = self._fetch_thread_summaries(company_id)
        thread_by_worker: dict[str, dict[str, Any]] = {}
        for thread in threads:
            wid = str(thread.get("worker_id") or "")
            if not wid:
                continue
            existing = thread_by_worker.get(wid)
            if not existing:
                thread_by_worker[wid] = thread
                continue
            existing_ts = str(existing.get("last_message_at") or existing.get("updated_at") or "")
            next_ts = str(thread.get("last_message_at") or thread.get("updated_at") or "")
            if next_ts > existing_ts:
                thread_by_worker[wid] = thread

        directory: list[dict[str, Any]] = []
        for worker in workers:
            wid = str(worker["id"])
            thread = thread_by_worker.get(wid)
            summary = summaries.get(str(thread["id"])) if thread else {}
            directory.append(
                {
                    "id": str(thread["id"]) if thread else "",
                    "worker_id": wid,
                    "first_name": worker["first_name"],
                    "last_name": worker["last_name"],
                    "badge_id": worker["badge_id"],
                    "status": worker["status"],
                    "subject": str(thread["subject"]) if thread else "general",
                    "last_message_at": summary.get("last_message_at")
                    or (thread.get("last_message_at") if thread else None),
                    "updated_at": thread.get("updated_at") if thread else None,
                    "last_message_preview": summary.get("last_message_preview"),
                    "last_message_sender_type": summary.get("last_message_sender_type"),
                    "unread_count": int(summary.get("unread_count") or 0),
                    "hasThread": bool(thread),
                }
            )

        directory.sort(
            key=lambda row: (
                0 if row.get("last_message_at") else 1,
                str(row.get("last_message_at") or row.get("updated_at") or ""),
            ),
            reverse=True,
        )
        return directory

    def get_or_create_worker_thread(
        self,
        *,
        company_id: str,
        worker_id: str,
        subject: str,
        created_by_user_id: str | None = None,
    ) -> str:
        clean_subject = str(subject or "general").strip() or "general"
        existing = self.db.execute(
            "SELECT id FROM chat_threads WHERE company_id = ? AND worker_id = ? AND subject = ?",
            (company_id, worker_id, clean_subject),
        ).fetchone()
        if existing:
            return str(existing["id"])
        thread_id = f"cht-{uuid.uuid4().hex[:16]}"
        now = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO chat_threads
            (id, company_id, worker_id, subject, status, created_at, updated_at, last_message_at, created_by_user_id)
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)
            """,
            (thread_id, company_id, worker_id, clean_subject, now, now, now, created_by_user_id or ""),
        )
        self.db.commit()
        return thread_id

    def list_messages(self, thread_id: str, company_id: str) -> list[dict[str, Any]]:
        thread_row = self.db.execute(
            "SELECT last_worker_read_at, last_admin_read_at FROM chat_threads WHERE id = ? AND company_id = ?",
            (thread_id, company_id),
        ).fetchone()
        last_worker_read = str(thread_row["last_worker_read_at"] or "") if thread_row else ""
        last_admin_read = str(thread_row["last_admin_read_at"] or "") if thread_row else ""
        rows = self.db.execute(
            """
            SELECT m.*, a.id AS attachment_id, a.filename AS attachment_filename, a.content_type AS attachment_content_type,
                   a.file_size AS attachment_file_size, a.e2e_meta AS attachment_e2e_meta
            FROM chat_messages m
            LEFT JOIN chat_attachments a ON a.message_id = m.id
            WHERE m.thread_id = ? AND m.company_id = ?
            ORDER BY m.created_at ASC
            """,
            (thread_id, company_id),
        ).fetchall()
        messages: dict[str, dict[str, Any]] = {}
        for row in rows:
            msg_id = str(row["id"])
            entry = messages.setdefault(
                msg_id,
                {
                    "id": msg_id,
                    "threadId": row["thread_id"],
                    "companyId": row["company_id"],
                    "workerId": row["worker_id"],
                    "senderType": row["sender_type"],
                    "senderUserId": row["sender_user_id"],
                    "senderWorkerId": row["sender_worker_id"],
                    "body": maybe_decrypt_field(row["body"], company_id=str(row["company_id"] or "")),
                    "createdAt": row["created_at"],
                    "readAt": row["read_at"],
                    "attachments": [],
                },
            )
            if row["attachment_id"]:
                attach_payload = {
                    "id": row["attachment_id"],
                    "filename": row["attachment_filename"],
                    "contentType": row["attachment_content_type"],
                    "fileSize": row["attachment_file_size"],
                }
                e2e_meta = str(row["attachment_e2e_meta"] or "").strip()
                if e2e_meta:
                    attach_payload["e2eMeta"] = e2e_meta
                    attach_payload["encrypted"] = True
                entry["attachments"].append(attach_payload)
        result = list(messages.values())
        for entry in result:
            created = str(entry.get("createdAt") or "")
            sender = str(entry.get("senderType") or "")
            if sender == "worker":
                entry["readByRecipient"] = bool(last_admin_read and created and last_admin_read >= created)
            else:
                entry["readByRecipient"] = bool(last_worker_read and created and last_worker_read >= created)
        return result

    def create_message(
        self,
        *,
        thread_id: str,
        company_id: str,
        worker_id: str,
        sender_type: str,
        sender_user_id: str | None,
        sender_worker_id: str | None,
        body: str,
        allow_plaintext_e2e_fallback: bool = False,
    ) -> dict[str, Any]:
        if not body.strip():
            raise ValueError("message_required")
        try:
            return self._create_message_record(
                thread_id=thread_id,
                company_id=company_id,
                worker_id=worker_id,
                sender_type=sender_type,
                sender_user_id=sender_user_id,
                sender_worker_id=sender_worker_id,
                body=body,
                allow_plaintext_e2e_fallback=allow_plaintext_e2e_fallback,
            )
        except ValueError:
            raise
        except Exception:
            self._ensure_schema()
            return self._create_message_record(
                thread_id=thread_id,
                company_id=company_id,
                worker_id=worker_id,
                sender_type=sender_type,
                sender_user_id=sender_user_id,
                sender_worker_id=sender_worker_id,
                body=body,
                allow_plaintext_e2e_fallback=allow_plaintext_e2e_fallback,
            )

    def _create_message_record(
        self,
        *,
        thread_id: str,
        company_id: str,
        worker_id: str,
        sender_type: str,
        sender_user_id: str | None,
        sender_worker_id: str | None,
        body: str,
        silent_side_effects: bool = False,
        allow_plaintext_e2e_fallback: bool = False,
    ) -> dict[str, Any]:
        message_id = f"msg-{uuid.uuid4().hex[:16]}"
        now = utc_now_iso()
        plain_body = body.strip()
        if is_e2e_chat_required(self.db, company_id, worker_id=worker_id) and not allow_plaintext_e2e_fallback:
            assert_e2e_message_body(plain_body)
        stored_body = maybe_encrypt_field(plain_body, company_id=company_id)
        encrypted_preview = is_e2e_envelope(plain_body)
        self.db.execute(
            """
            INSERT INTO chat_messages
            (id, thread_id, company_id, worker_id, sender_type, sender_user_id, sender_worker_id, body, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (message_id, thread_id, company_id, worker_id, sender_type, sender_user_id, sender_worker_id, stored_body, now),
        )
        self.db.execute(
            """
            UPDATE chat_threads
            SET updated_at = ?, last_message_at = ?,
                last_worker_read_at = CASE WHEN ? = 'worker' THEN ? ELSE last_worker_read_at END,
                last_admin_read_at = CASE WHEN ? != 'worker' THEN ? ELSE last_admin_read_at END
            WHERE id = ? AND company_id = ?
            """,
            (now, now, sender_type, now, sender_type, now, thread_id, company_id),
        )
        self.db.commit()

        event_payload = {
            "threadId": thread_id,
            "messageId": message_id,
            "workerId": worker_id,
            "senderType": sender_type,
            "preview": "encrypted" if encrypted_preview else plain_body[:120],
        }
        try:
            publish_event("chat.message_created", company_id, event_payload, actor_id=sender_user_id or sender_worker_id or "")
        except Exception:
            pass

        notify_body = "Neue verschlüsselte Nachricht" if encrypted_preview else plain_body
        try:
            if not silent_side_effects:
                if sender_type == "worker":
                    self._notify_company_side(company_id, worker_id, notify_body)
                else:
                    notify_worker_mitteilung(
                        self.db,
                        worker_id,
                        notif_type="worker_chat",
                        title="Neue Nachricht",
                        message=notify_body[:280] if not encrypted_preview else "Neue verschlüsselte Nachricht",
                        action_url="chat",
                        push_tag="worker-chat",
                        send_email=False,
                    )
        except Exception:
            pass

        try:
            self.db.commit()
        except Exception:
            pass

        return {
            "id": message_id,
            "threadId": thread_id,
            "companyId": company_id,
            "workerId": worker_id,
            "senderType": sender_type,
            "senderUserId": sender_user_id,
            "senderWorkerId": sender_worker_id,
            "body": plain_body,
            "createdAt": now,
            "attachments": [],
        }

    def broadcast_to_workers(
        self,
        *,
        company_id: str,
        worker_ids: list[str],
        title: str,
        message: str,
        sender_user_id: str,
    ) -> int:
        """Post one admin chat message per worker thread (plus push via create_message)."""
        title = (title or "").strip()
        message = (message or "").strip()
        if not message:
            return 0
        if title and title.lower() not in {"mitteilung", "message from employer", "nachricht vom arbeitgeber"}:
            body = f"{title}\n\n{message}"
        else:
            body = message
        sent = 0
        for worker_id in worker_ids:
            try:
                thread_id = self.get_or_create_worker_thread(
                    company_id=company_id,
                    worker_id=worker_id,
                    subject="general",
                    created_by_user_id=sender_user_id,
                )
                self.create_message(
                    thread_id=thread_id,
                    company_id=company_id,
                    worker_id=worker_id,
                    sender_type="admin",
                    sender_user_id=sender_user_id,
                    sender_worker_id=None,
                    body=body,
                    allow_plaintext_e2e_fallback=True,
                )
                sent += 1
            except Exception:
                continue
        return sent

    def save_attachment(
        self,
        *,
        message_id: str,
        company_id: str,
        worker_id: str,
        filename: str,
        content_type: str,
        blob: bytes,
        storage_root: Path | None = None,
        e2e_meta: str | None = None,
        encrypted: bool = False,
    ) -> dict[str, Any]:
        from backend.server import CHAT_UPLOAD_DIR, _stored_file_path

        if is_e2e_attachment_required(self.db, company_id, worker_id=worker_id):
            assert_e2e_attachment(
                e2e_meta=str(e2e_meta or ""),
                content_type=str(content_type or ""),
                encrypted=bool(encrypted),
            )
        attachment_id = f"att-{uuid.uuid4().hex[:16]}"
        now = utc_now_iso()
        target_dir = CHAT_UPLOAD_DIR / company_id / worker_id
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{attachment_id}_{Path(filename or 'upload.bin').name}"
        file_path = target_dir / safe_name
        file_path.write_bytes(blob)
        stored_path = _stored_file_path(file_path)
        meta = str(e2e_meta or "").strip()
        cols = self._table_columns("chat_attachments")
        if "e2e_meta" in cols:
            self.db.execute(
                """
                INSERT INTO chat_attachments
                (id, message_id, company_id, worker_id, filename, content_type, file_path, file_size, created_at, e2e_meta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attachment_id,
                    message_id,
                    company_id,
                    worker_id,
                    filename or "upload.bin",
                    content_type or "application/octet-stream",
                    stored_path,
                    len(blob),
                    now,
                    meta or None,
                ),
            )
        else:
            self.db.execute(
                """
                INSERT INTO chat_attachments
                (id, message_id, company_id, worker_id, filename, content_type, file_path, file_size, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attachment_id,
                    message_id,
                    company_id,
                    worker_id,
                    filename or "upload.bin",
                    content_type or "application/octet-stream",
                    stored_path,
                    len(blob),
                    now,
                ),
            )
        self.db.commit()
        payload = {
            "id": attachment_id,
            "filename": filename or "upload.bin",
            "contentType": content_type or "application/octet-stream",
            "fileSize": len(blob),
        }
        if meta:
            payload["e2eMeta"] = meta
            payload["encrypted"] = True
        return payload

    @staticmethod
    def resolve_storage_path(stored: str) -> Path | None:
        from backend.server import BASE_DIR, CHAT_UPLOAD_DIR

        raw = str(stored or "").strip()
        if not raw:
            return None
        candidates: list[Path] = [Path(raw)]
        base = Path(BASE_DIR)
        path = Path(raw)
        if not path.is_absolute():
            candidates.append(base / raw)
        normalized = raw.replace("\\", "/")
        chat_idx = normalized.find("/chat/")
        if chat_idx >= 0:
            chat_tail = normalized[chat_idx + len("/chat/") :]
            if chat_tail:
                candidates.append(CHAT_UPLOAD_DIR / chat_tail)
                candidates.append(base / "backend" / "uploads" / "chat" / chat_tail)
        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
        return None

    def resolve_attachment_path(self, row) -> Path | None:
        file_path = self.resolve_storage_path(str(row["file_path"] or ""))
        if file_path:
            return file_path
        worker_id = str(row["worker_id"] or "")
        company_id = str(row["company_id"] or "")
        filename = str(row["filename"] or "")
        if not worker_id or not filename:
            return None
        doc = self.db.execute(
            """
            SELECT file_path FROM worker_documents
            WHERE worker_id = ? AND company_id = ?
              AND (filename = ? OR file_path LIKE ?)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (worker_id, company_id, filename, f"%{filename}"),
        ).fetchone()
        if not doc:
            return None
        return self.resolve_storage_path(str(doc["file_path"] or ""))

    def mark_thread_read(self, *, thread_id: str, company_id: str, reader_type: str) -> None:
        now = utc_now_iso()
        if reader_type == "worker":
            self.db.execute(
                "UPDATE chat_threads SET last_worker_read_at = ?, updated_at = ? WHERE id = ? AND company_id = ?",
                (now, now, thread_id, company_id),
            )
        else:
            self.db.execute(
                "UPDATE chat_threads SET last_admin_read_at = ?, updated_at = ? WHERE id = ? AND company_id = ?",
                (now, now, thread_id, company_id),
            )
        self.db.commit()

    def delete_message(
        self,
        message_id: str,
        company_id: str,
        *,
        actor_type: str,
        actor_worker_id: str | None = None,
        actor_user_id: str | None = None,
    ) -> None:
        row = self.db.execute(
            """
            SELECT id, thread_id, sender_type, sender_worker_id, sender_user_id, created_at
            FROM chat_messages
            WHERE id = ? AND company_id = ?
            """,
            (message_id, company_id),
        ).fetchone()
        if not row:
            raise ValueError("message_not_found")
        sender_type = str(row["sender_type"] or "")
        if actor_type == "worker":
            if sender_type != "worker" or str(row["sender_worker_id"] or "") != str(actor_worker_id or ""):
                raise ValueError("forbidden")
        elif actor_type == "admin":
            if sender_type != "admin" or str(row["sender_user_id"] or "") != str(actor_user_id or ""):
                raise ValueError("forbidden")
        else:
            raise ValueError("forbidden")

        self.db.execute("DELETE FROM chat_attachments WHERE message_id = ?", (message_id,))
        self.db.execute("DELETE FROM chat_messages WHERE id = ? AND company_id = ?", (message_id, company_id))
        self.db.commit()

    def clear_thread_messages(
        self,
        thread_id: str,
        company_id: str,
        *,
        actor_type: str,
        actor_worker_id: str | None = None,
        actor_user_id: str | None = None,
        scope: str = "own",
    ) -> int:
        clean_scope = str(scope or "own").strip().lower()
        if clean_scope not in {"own", "all"}:
            raise ValueError("invalid_scope")
        if clean_scope == "all" and actor_type not in {"admin", "worker"}:
            raise ValueError("forbidden")
        rows = self.db.execute(
            """
            SELECT id, sender_type, sender_worker_id, sender_user_id
            FROM chat_messages
            WHERE thread_id = ? AND company_id = ?
            """,
            (thread_id, company_id),
        ).fetchall()
        deleted = 0
        for row in rows:
            sender_type = str(row["sender_type"] or "")
            if clean_scope == "all":
                allowed = True
            elif actor_type == "worker":
                allowed = sender_type == "worker" and str(row["sender_worker_id"] or "") == str(actor_worker_id or "")
            elif actor_type == "admin":
                allowed = sender_type == "admin" and str(row["sender_user_id"] or "") == str(actor_user_id or "")
            else:
                allowed = False
            if not allowed:
                continue
            message_id = str(row["id"])
            self.db.execute("DELETE FROM chat_attachments WHERE message_id = ?", (message_id,))
            self.db.execute("DELETE FROM chat_messages WHERE id = ? AND company_id = ?", (message_id, company_id))
            deleted += 1
        self.db.commit()
        return deleted

    def _notify_company_side(self, company_id: str, worker_id: str, body: str) -> None:
        try:
            self.db.execute(
                """
                INSERT INTO notifications
                (id, worker_id, company_id, type, title, message, action_url, created_at)
                VALUES (?, ?, ?, 'worker_chat_admin', 'Neue Mitarbeiter-Nachricht', ?, '/admin-v2/index.html', ?)
                """,
                (f"notif-{uuid.uuid4().hex[:16]}", worker_id, company_id, body[:280], utc_now_iso()),
            )
            self.db.commit()
        except Exception:
            pass

    def share_file_in_worker_thread(
        self,
        *,
        company_id: str,
        worker_id: str,
        filename: str,
        content_type: str,
        blob: bytes,
        body: str,
        sender_type: str,
        sender_user_id: str | None = None,
        sender_worker_id: str | None = None,
        storage_root: Path | None = None,
        subject: str = "general",
    ) -> dict[str, Any]:
        """Attach a file to the worker chat thread (admin or worker sender)."""
        clean_body = str(body or "").strip() or f"📎 {Path(filename or 'Unterlage').name}"
        thread_id = self.get_or_create_worker_thread(
            company_id=company_id,
            worker_id=worker_id,
            subject=subject,
            created_by_user_id=sender_user_id,
        )
        message = self._create_message_record(
            thread_id=thread_id,
            company_id=company_id,
            worker_id=worker_id,
            sender_type=sender_type,
            sender_user_id=sender_user_id,
            sender_worker_id=sender_worker_id,
            body=clean_body,
            silent_side_effects=True,
        )
        attachment = self.save_attachment(
            message_id=str(message["id"]),
            company_id=company_id,
            worker_id=worker_id,
            filename=filename,
            content_type=content_type,
            blob=blob,
        )
        message["attachments"] = [attachment]
        return {"threadId": thread_id, "message": message}

    def register_worker_chat_submission(
        self,
        *,
        worker_id: str,
        company_id: str,
        filename: str,
        content_type: str,
        blob: bytes,
        doc_type_raw: str = "sonstiges",
    ) -> str | None:
        """Store a worker chat attachment also in worker_documents for HR review."""
        import secrets

        from backend.app.platform.worker_documents import normalize_doc_type
        from backend.server import (
            ALLOWED_UPLOAD_MIMETYPES,
            DOCS_UPLOAD_DIR,
            MAX_IMAP_ATTACHMENT_BYTES,
            _sanitize_attachment_filename,
            _stored_file_path,
            now_iso,
            unlock_worker_if_documents_valid,
            utc_now,
        )

        doc_type = normalize_doc_type(str(doc_type_raw or "sonstiges").strip() or "sonstiges")
        mime = str(content_type or "application/octet-stream").lower().split(";")[0].strip()
        if mime not in ALLOWED_UPLOAD_MIMETYPES or not blob:
            return None
        if len(blob) > MAX_IMAP_ATTACHMENT_BYTES:
            return None

        worker = self.db.execute(
            "SELECT id, company_id, badge_id FROM workers WHERE id = ? AND company_id = ? AND deleted_at IS NULL",
            (worker_id, company_id),
        ).fetchone()
        if not worker:
            return None

        worker_doc_dir = (DOCS_UPLOAD_DIR / worker_id).resolve()
        base_upload_root = DOCS_UPLOAD_DIR.resolve()
        if worker_doc_dir != base_upload_root and base_upload_root not in worker_doc_dir.parents:
            return None
        worker_doc_dir.mkdir(parents=True, exist_ok=True)

        safe_name = _sanitize_attachment_filename(filename or "upload.bin")
        ts = utc_now().strftime("%Y%m%d_%H%M%S")
        file_path = (worker_doc_dir / f"{doc_type}_{ts}_{safe_name}").resolve()
        if worker_doc_dir not in file_path.parents:
            return None
        file_path.write_bytes(blob)
        stored_path = _stored_file_path(file_path)
        doc_id = f"doc-{secrets.token_hex(8)}"
        self.db.execute(
            """
            INSERT INTO worker_documents
               (id, worker_id, company_id, doc_type, filename, file_path, file_size,
                source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes, expiry_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                doc_id,
                worker_id,
                company_id,
                doc_type,
                safe_name,
                stored_path,
                len(blob),
                "",
                None,
                "",
                now_iso(),
                "Eingereicht über Chat",
                None,
            ),
        )
        try:
            unlock_worker_if_documents_valid(self.db, dict(worker), actor={"id": worker_id, "role": "worker"})
        except Exception:
            pass
        self.db.commit()
        return doc_id
