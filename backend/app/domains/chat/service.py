from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.platform.events.bus import publish_event
from backend.app.platform.notifications.worker_mitteilung import notify_worker_mitteilung
from backend.app.platform.push.delivery import deliver_worker_push


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        return [dict(row) for row in rows]

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
            directory.append(
                {
                    "id": str(thread["id"]) if thread else "",
                    "worker_id": wid,
                    "first_name": worker["first_name"],
                    "last_name": worker["last_name"],
                    "badge_id": worker["badge_id"],
                    "status": worker["status"],
                    "subject": str(thread["subject"]) if thread else "general",
                    "last_message_at": thread.get("last_message_at") if thread else None,
                    "updated_at": thread.get("updated_at") if thread else None,
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
            SELECT m.*, a.id AS attachment_id, a.filename AS attachment_filename, a.content_type AS attachment_content_type, a.file_size AS attachment_file_size
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
                    "body": row["body"],
                    "createdAt": row["created_at"],
                    "readAt": row["read_at"],
                    "attachments": [],
                },
            )
            if row["attachment_id"]:
                entry["attachments"].append(
                    {
                        "id": row["attachment_id"],
                        "filename": row["attachment_filename"],
                        "contentType": row["attachment_content_type"],
                        "fileSize": row["attachment_file_size"],
                    }
                )
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
    ) -> dict[str, Any]:
        message_id = f"msg-{uuid.uuid4().hex[:16]}"
        now = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO chat_messages
            (id, thread_id, company_id, worker_id, sender_type, sender_user_id, sender_worker_id, body, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (message_id, thread_id, company_id, worker_id, sender_type, sender_user_id, sender_worker_id, body.strip(), now),
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
            "preview": body.strip()[:120],
        }
        try:
            publish_event("chat.message_created", company_id, event_payload, actor_id=sender_user_id or sender_worker_id or "")
        except Exception:
            pass

        try:
            if sender_type == "worker":
                self._notify_company_side(company_id, worker_id, body.strip())
            else:
                notify_worker_mitteilung(
                    self.db,
                    worker_id,
                    notif_type="worker_chat",
                    title="Neue Nachricht",
                    message=body.strip()[:280],
                    action_url="chat",
                    push_tag="worker-chat",
                    send_email=False,
                )
                try:
                    deliver_worker_push(
                        self.db,
                        worker_id,
                        "Neue Nachricht",
                        body.strip()[:180],
                        tag="worker-chat",
                        company_id=company_id,
                    )
                except Exception:
                    pass
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
            "body": body.strip(),
            "createdAt": now,
            "attachments": [],
        }

    def save_attachment(
        self,
        *,
        message_id: str,
        company_id: str,
        worker_id: str,
        filename: str,
        content_type: str,
        blob: bytes,
        storage_root: Path,
    ) -> dict[str, Any]:
        attachment_id = f"att-{uuid.uuid4().hex[:16]}"
        now = utc_now_iso()
        target_dir = storage_root / "chat" / company_id / worker_id
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{attachment_id}_{Path(filename or 'upload.bin').name}"
        file_path = target_dir / safe_name
        file_path.write_bytes(blob)
        self.db.execute(
            """
            INSERT INTO chat_attachments
            (id, message_id, company_id, worker_id, filename, content_type, file_path, file_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (attachment_id, message_id, company_id, worker_id, filename or "upload.bin", content_type or "application/octet-stream", str(file_path), len(blob), now),
        )
        self.db.commit()
        return {
            "id": attachment_id,
            "filename": filename or "upload.bin",
            "contentType": content_type or "application/octet-stream",
            "fileSize": len(blob),
        }

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
