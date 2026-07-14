"""Voice call session + WebRTC signaling (audio only)."""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.platform.events.bus import publish_event
from backend.app.core.platform_env import platform_env

RING_TIMEOUT_SECONDS = 45
ACTIVE_STATUSES = frozenset({"ringing", "accepted"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ice_servers() -> list[dict[str, Any]]:
    raw_json = platform_env("ICE_SERVERS_JSON")
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list) and parsed:
                return parsed
        except Exception:
            pass
    servers: list[dict[str, Any]] = [
        {"urls": "stun:stun.l.google.com:19302"},
        {"urls": "stun:stun1.l.google.com:19302"},
        {"urls": "stun:stun.cloudflare.com:3478"},
    ]
    turn_url = platform_env("TURN_URL")
    if turn_url:
        entry: dict[str, Any] = {"urls": turn_url}
        username = platform_env("TURN_USERNAME")
        password = platform_env("TURN_PASSWORD")
        if username:
            entry["username"] = username
        if password:
            entry["credential"] = password
        servers.append(entry)
        if turn_url.startswith("turn:") and not turn_url.startswith("turns:"):
            tls_entry = dict(entry)
            tls_entry["urls"] = "turns:" + turn_url[5:]
            servers.append(tls_entry)
    return servers


def ice_servers_diagnostics() -> dict[str, Any]:
    """Non-secret snapshot for admin health checks (no credentials)."""
    servers = ice_servers()
    urls: list[str] = []
    turn_configured = False
    has_credentials = bool(platform_env("TURN_USERNAME") and platform_env("TURN_PASSWORD"))
    using_json = bool(platform_env("ICE_SERVERS_JSON"))
    for item in servers:
        raw_urls = item.get("urls")
        if isinstance(raw_urls, list):
            batch = [str(u) for u in raw_urls]
        else:
            batch = [str(raw_urls or "")]
        for url in batch:
            if not url:
                continue
            urls.append(url)
            if url.startswith("turn:") or url.startswith("turns:"):
                turn_configured = True
    return {
        "turnConfigured": turn_configured,
        "turnCredentialsConfigured": has_credentials or using_json,
        "iceServersJsonOverride": using_json,
        "primaryTurnUrl": platform_env("TURN_URL"),
        "serverCount": len(servers),
        "urls": urls,
    }


class VoiceCallService:
    def __init__(self, db):
        self.db = db
        self._ensure_schema()

    def _table_columns(self, table: str) -> set[str]:
        try:
            return {str(row[1]) for row in self.db.execute(f"PRAGMA table_info({table})").fetchall()}
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
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_voice_calls (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                caller_user_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ringing',
                created_at TEXT NOT NULL,
                answered_at TEXT,
                ended_at TEXT,
                end_reason TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_voice_call_signals (
                id TEXT PRIMARY KEY,
                call_id TEXT NOT NULL,
                sender_role TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        try:
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_voice_calls_worker_status ON chat_voice_calls(worker_id, status, created_at DESC)"
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_voice_call_signals_call ON chat_voice_call_signals(call_id, created_at ASC)"
            )
        except Exception:
            pass

    def _row_to_call(self, row) -> dict[str, Any]:
        if not row:
            return {}
        keys = row.keys() if hasattr(row, "keys") else []
        return {
            "id": row["id"] if "id" in keys else "",
            "companyId": row["company_id"] if "company_id" in keys else "",
            "workerId": row["worker_id"] if "worker_id" in keys else "",
            "callerUserId": row["caller_user_id"] if "caller_user_id" in keys else "",
            "status": row["status"] if "status" in keys else "",
            "createdAt": row["created_at"] if "created_at" in keys else "",
            "answeredAt": row["answered_at"] if "answered_at" in keys else None,
            "endedAt": row["ended_at"] if "ended_at" in keys else None,
            "endReason": row["end_reason"] if "end_reason" in keys else "",
        }

    def _enrich_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not payload:
            return payload
        payload = dict(payload)
        payload["iceServers"] = ice_servers()
        caller_id = str(payload.get("callerUserId") or "").strip()
        if caller_id:
            try:
                user = self.db.execute(
                    "SELECT name, username FROM users WHERE id = ?",
                    (caller_id,),
                ).fetchone()
                if user:
                    name = str(user["name"] or user["username"] or "").strip()
                    if name:
                        payload["callerName"] = name
            except Exception:
                pass
        company_id = str(payload.get("companyId") or "").strip()
        if company_id:
            try:
                company = self.db.execute(
                    "SELECT name FROM companies WHERE id = ?",
                    (company_id,),
                ).fetchone()
                if company:
                    cname = str(company["name"] or "").strip()
                    if cname:
                        payload["companyName"] = cname
            except Exception:
                pass
        return payload

    def _call_duration_seconds(self, call: dict[str, Any]) -> int:
        answered = str(call.get("answeredAt") or "").strip()
        ended = str(call.get("endedAt") or "").strip()
        if not answered or not ended:
            return 0
        try:
            start = datetime.fromisoformat(answered.replace("Z", "+00:00"))
            finish = datetime.fromisoformat(ended.replace("Z", "+00:00"))
            return max(0, int((finish - start).total_seconds()))
        except Exception:
            return 0

    def _log_call_to_chat(self, call: dict[str, Any], *, status: str, reason: str, role: str) -> None:
        company_id = str(call.get("companyId") or "").strip()
        worker_id = str(call.get("workerId") or "").strip()
        caller_user_id = str(call.get("callerUserId") or "").strip()
        if not company_id or not worker_id:
            return
        duration_sec = self._call_duration_seconds(call)
        call_id = str(call.get("id") or "").strip()
        body = f"@voice-call|status={status}|duration={duration_sec}|reason={reason}|role={role}"
        if call_id:
            body += f"|callId={call_id}"
        try:
            from backend.app.domains.chat.service import ChatService

            chat = ChatService(self.db)
            thread_id = chat.get_or_create_worker_thread(
                company_id=company_id,
                worker_id=worker_id,
                subject="general",
                created_by_user_id=caller_user_id or None,
            )
            sender_type = "worker" if role == "worker" else "admin"
            chat.create_message(
                thread_id=thread_id,
                company_id=company_id,
                worker_id=worker_id,
            sender_type=sender_type,
            sender_user_id=(caller_user_id or None) if sender_type == "admin" else None,
            sender_worker_id=worker_id if sender_type == "worker" else None,
                body=body,
                allow_plaintext_e2e_fallback=True,
            )
            self.db.commit()
        except Exception:
            pass

    def expire_stale_calls(self) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=RING_TIMEOUT_SECONDS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = self.db.execute(
            """
            SELECT id, company_id, worker_id FROM chat_voice_calls
            WHERE status = 'ringing' AND created_at < ?
            """,
            (cutoff,),
        ).fetchall()
        count = 0
        now = utc_now_iso()
        for row in rows:
            self.db.execute(
                """
                UPDATE chat_voice_calls
                SET status = 'missed', ended_at = ?, end_reason = 'timeout'
                WHERE id = ? AND status = 'ringing'
                """,
                (now, row["id"]),
            )
            count += 1
            try:
                publish_event(
                    "voice_call.missed",
                    row["company_id"],
                    {"callId": row["id"], "workerId": row["worker_id"]},
                )
            except Exception:
                pass
            try:
                missed_call = self.get_call(str(row["id"]))
                self._log_call_to_chat(missed_call, status="missed", reason="timeout", role="system")
            except Exception:
                pass
        return count

    def _worker_has_active_call(self, worker_id: str) -> bool:
        self.expire_stale_calls()
        row = self.db.execute(
            """
            SELECT id FROM chat_voice_calls
            WHERE worker_id = ? AND status IN ('ringing', 'accepted')
            LIMIT 1
            """,
            (worker_id,),
        ).fetchone()
        return bool(row)

    def start_call(self, *, company_id: str, worker_id: str, caller_user_id: str) -> dict[str, Any]:
        self.expire_stale_calls()
        worker = self.db.execute(
            """
            SELECT id, first_name, last_name FROM workers
            WHERE id = ? AND company_id = ? AND deleted_at IS NULL
            """,
            (worker_id, company_id),
        ).fetchone()
        if not worker:
            raise ValueError("worker_not_found")
        if self._worker_has_active_call(worker_id):
            raise ValueError("worker_busy")

        call_id = f"vc-{uuid.uuid4().hex[:16]}"
        now = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO chat_voice_calls (id, company_id, worker_id, caller_user_id, status, created_at)
            VALUES (?, ?, ?, ?, 'ringing', ?)
            """,
            (call_id, company_id, worker_id, caller_user_id, now),
        )
        try:
            from backend.app.platform.push.delivery import deliver_worker_push

            deliver_worker_push(
                self.db,
                worker_id,
                title="Eingehender Anruf",
                body="Ihr Arbeitgeber ruft an — sicherer Sprachkanal.",
                tag="voice-call",
                company_id=company_id,
                extra={"callId": call_id, "type": "voice_call_incoming"},
            )
        except Exception:
            pass
        try:
            publish_event(
                "voice_call.incoming",
                company_id,
                {"callId": call_id, "workerId": worker_id, "callerUserId": caller_user_id},
                actor_id=caller_user_id,
            )
        except Exception:
            pass
        return self._enrich_call(
            {
                **self._row_to_call(
                    self.db.execute("SELECT * FROM chat_voice_calls WHERE id = ?", (call_id,)).fetchone()
                ),
            }
        )

    def get_call(self, call_id: str) -> dict[str, Any]:
        self.expire_stale_calls()
        row = self.db.execute("SELECT * FROM chat_voice_calls WHERE id = ?", (call_id,)).fetchone()
        if not row:
            raise ValueError("call_not_found")
        payload = self._row_to_call(row)
        return self._enrich_call(payload)

    def get_incoming_for_worker(self, worker_id: str) -> dict[str, Any] | None:
        self.expire_stale_calls()
        row = self.db.execute(
            """
            SELECT * FROM chat_voice_calls
            WHERE worker_id = ? AND status = 'ringing'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (worker_id,),
        ).fetchone()
        if not row:
            return None
        payload = self._row_to_call(row)
        return self._enrich_call(payload)

    def accept_call(self, call_id: str, *, role: str) -> dict[str, Any]:
        call = self.get_call(call_id)
        if call.get("status") != "ringing":
            raise ValueError("call_not_ringing")
        if role != "worker":
            raise ValueError("forbidden")
        now = utc_now_iso()
        self.db.execute(
            """
            UPDATE chat_voice_calls
            SET status = 'accepted', answered_at = ?
            WHERE id = ? AND status = 'ringing'
            """,
            (now, call_id),
        )
        try:
            publish_event(
                "voice_call.accepted",
                call.get("companyId"),
                {"callId": call_id, "workerId": call.get("workerId")},
            )
        except Exception:
            pass
        return self.get_call(call_id)

    def decline_call(self, call_id: str, *, role: str) -> dict[str, Any]:
        call = self.get_call(call_id)
        if call.get("status") not in ACTIVE_STATUSES:
            raise ValueError("call_not_active")
        if role == "worker" and call.get("status") != "ringing":
            raise ValueError("call_not_ringing")
        now = utc_now_iso()
        status = "declined" if role == "worker" else "ended"
        reason = "declined_by_worker" if role == "worker" else "cancelled_by_admin"
        self.db.execute(
            """
            UPDATE chat_voice_calls
            SET status = ?, ended_at = ?, end_reason = ?
            WHERE id = ? AND status IN ('ringing', 'accepted')
            """,
            (status, now, reason, call_id),
        )
        try:
            publish_event(
                "voice_call.declined" if role == "worker" else "voice_call.ended",
                call.get("companyId"),
                {"callId": call_id, "workerId": call.get("workerId"), "reason": reason},
            )
        except Exception:
            pass
        updated = self.get_call(call_id)
        log_status = "declined" if role == "worker" else "cancelled"
        self._log_call_to_chat(updated, status=log_status, reason=reason, role=role)
        return updated

    def end_call(self, call_id: str, *, role: str, reason: str = "hangup") -> dict[str, Any]:
        call = self.get_call(call_id)
        if call.get("status") not in ACTIVE_STATUSES:
            raise ValueError("call_not_active")
        now = utc_now_iso()
        end_reason = reason or ("ended_by_worker" if role == "worker" else "ended_by_admin")
        self.db.execute(
            """
            UPDATE chat_voice_calls
            SET status = 'ended', ended_at = ?, end_reason = ?
            WHERE id = ? AND status IN ('ringing', 'accepted')
            """,
            (now, end_reason, call_id),
        )
        self.add_signal(call_id, sender_role=role, signal_type="hangup", payload={"reason": end_reason})
        try:
            publish_event(
                "voice_call.ended",
                call.get("companyId"),
                {"callId": call_id, "workerId": call.get("workerId"), "reason": end_reason},
            )
        except Exception:
            pass
        updated = self.get_call(call_id)
        self._log_call_to_chat(updated, status="ended", reason=end_reason, role=role)
        return updated

    def add_signal(self, call_id: str, *, sender_role: str, signal_type: str, payload: Any) -> dict[str, Any]:
        call = self.get_call(call_id)
        if call.get("status") not in ACTIVE_STATUSES and signal_type != "hangup":
            raise ValueError("call_not_active")
        allowed = {"offer", "answer", "ice-candidate", "hangup"}
        stype = str(signal_type or "").strip().lower()
        if stype not in allowed:
            raise ValueError("invalid_signal_type")
        role = str(sender_role or "").strip().lower()
        if role not in {"admin", "worker"}:
            raise ValueError("invalid_sender_role")
        if isinstance(payload, str):
            payload_obj = {"sdp": payload}
        elif isinstance(payload, dict):
            payload_obj = payload
        else:
            payload_obj = {}
        signal_id = f"vs-{secrets.token_urlsafe(12)}"
        now = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO chat_voice_call_signals (id, call_id, sender_role, signal_type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (signal_id, call_id, role, stype, json.dumps(payload_obj, ensure_ascii=False), now),
        )
        try:
            publish_event(
                "voice_call.signal",
                call.get("companyId"),
                {
                    "callId": call_id,
                    "signalId": signal_id,
                    "senderRole": role,
                    "signalType": stype,
                    "workerId": call.get("workerId"),
                },
            )
        except Exception:
            pass
        return {"id": signal_id, "callId": call_id, "signalType": stype, "createdAt": now}

    def list_signals(self, call_id: str, *, for_role: str, since_id: str = "") -> list[dict[str, Any]]:
        self.get_call(call_id)
        peer_role = "worker" if for_role == "admin" else "admin"
        params: list[Any] = [call_id, peer_role]
        sql = """
            SELECT id, call_id, sender_role, signal_type, payload_json, created_at
            FROM chat_voice_call_signals
            WHERE call_id = ? AND sender_role = ?
        """
        if since_id:
            row = self.db.execute("SELECT created_at FROM chat_voice_call_signals WHERE id = ?", (since_id,)).fetchone()
            if row:
                sql += " AND created_at > ?"
                params.append(row["created_at"])
        sql += " ORDER BY created_at ASC LIMIT 200"
        rows = self.db.execute(sql, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            out.append(
                {
                    "id": row["id"],
                    "callId": row["call_id"],
                    "senderRole": row["sender_role"],
                    "signalType": row["signal_type"],
                    "payload": payload,
                    "createdAt": row["created_at"],
                }
            )
        return out

    def list_calls(
        self,
        *,
        company_id: str,
        worker_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.expire_stale_calls()
        clean_limit = max(1, min(int(limit or 50), 200))
        params: list[Any] = [company_id]
        sql = """
            SELECT * FROM chat_voice_calls
            WHERE company_id = ?
        """
        if worker_id:
            sql += " AND worker_id = ?"
            params.append(worker_id)
        sql += " ORDER BY datetime(created_at) DESC LIMIT ?"
        params.append(clean_limit)
        rows = self.db.execute(sql, tuple(params)).fetchall()
        history: list[dict[str, Any]] = []
        for row in rows:
            payload = self._enrich_call(self._row_to_call(row))
            payload["durationSec"] = self._call_duration_seconds(payload)
            history.append(payload)
        return history

    def count_missed_calls(self, *, company_id: str, worker_id: str | None = None) -> int:
        self.expire_stale_calls()
        params: list[Any] = [company_id]
        sql = """
            SELECT COUNT(*) AS c FROM chat_voice_calls
            WHERE company_id = ? AND status = 'missed'
        """
        if worker_id:
            sql += " AND worker_id = ?"
            params.append(worker_id)
        row = self.db.execute(sql, tuple(params)).fetchone()
        return int(row["c"] if row and "c" in row.keys() else 0)

    def request_worker_callback(
        self,
        *,
        company_id: str,
        worker_id: str,
        call_id: str | None = None,
    ) -> dict[str, Any]:
        self.expire_stale_calls()
        call: dict[str, Any]
        if call_id:
            call = self.get_call(call_id)
            if str(call.get("workerId") or "") != str(worker_id):
                raise ValueError("forbidden")
            if str(call.get("companyId") or "") != str(company_id):
                raise ValueError("forbidden")
        else:
            row = self.db.execute(
                """
                SELECT * FROM chat_voice_calls
                WHERE company_id = ? AND worker_id = ? AND status IN ('missed', 'declined', 'ended')
                ORDER BY datetime(created_at) DESC
                LIMIT 1
                """,
                (company_id, worker_id),
            ).fetchone()
            if not row:
                raise ValueError("call_not_found")
            call = self._row_to_call(row)

        ref_id = str(call.get("id") or "")
        self._log_call_to_chat(
            {**call, "companyId": company_id, "workerId": worker_id},
            status="callback_requested",
            reason="worker_requested",
            role="worker",
        )
        try:
            from backend.app.platform.inbox.events import notify_inbox_changed

            notify_inbox_changed(company_id, source="voice_call_callback")
        except Exception:
            pass
        try:
            publish_event(
                "voice_call.callback_requested",
                company_id,
                {"callId": ref_id, "workerId": worker_id},
            )
        except Exception:
            pass
        return {"ok": True, "callId": ref_id}

    def list_calls(
        self,
        *,
        company_id: str,
        worker_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.expire_stale_calls()
        clean_limit = max(1, min(int(limit or 50), 200))
        params: list[Any] = [company_id]
        sql = """
            SELECT * FROM chat_voice_calls
            WHERE company_id = ?
        """
        if worker_id:
            sql += " AND worker_id = ?"
            params.append(worker_id)
        sql += " ORDER BY datetime(created_at) DESC LIMIT ?"
        params.append(clean_limit)
        rows = self.db.execute(sql, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            payload = self._enrich_call(self._row_to_call(row))
            payload["durationSec"] = self._call_duration_seconds(payload)
            out.append(payload)
        return out

    def count_missed_calls(self, *, company_id: str, worker_id: str | None = None) -> int:
        self.expire_stale_calls()
        params: list[Any] = [company_id]
        sql = """
            SELECT COUNT(*) AS c FROM chat_voice_calls
            WHERE company_id = ? AND status = 'missed'
        """
        if worker_id:
            sql += " AND worker_id = ?"
            params.append(worker_id)
        row = self.db.execute(sql, tuple(params)).fetchone()
        return int(row["c"] if row and "c" in row.keys() else 0)

    def request_worker_callback(
        self,
        *,
        company_id: str,
        worker_id: str,
        call_id: str | None = None,
    ) -> dict[str, Any]:
        self.expire_stale_calls()
        call: dict[str, Any]
        if call_id:
            call = self.get_call(call_id)
            if str(call.get("workerId") or "") != str(worker_id):
                raise ValueError("forbidden")
            if str(call.get("companyId") or "") != str(company_id):
                raise ValueError("forbidden")
        else:
            row = self.db.execute(
                """
                SELECT * FROM chat_voice_calls
                WHERE company_id = ? AND worker_id = ? AND status IN ('missed', 'declined', 'ended', 'cancelled')
                ORDER BY datetime(created_at) DESC
                LIMIT 1
                """,
                (company_id, worker_id),
            ).fetchone()
            if not row:
                raise ValueError("call_not_found")
            call = self._row_to_call(row)

        ref_id = str(call.get("id") or "")
        body = f"@voice-call|status=callback_requested|duration=0|reason=worker_requested|role=worker|callId={ref_id}"
        self._log_call_to_chat(
            {**call, "companyId": company_id, "workerId": worker_id},
            status="callback_requested",
            reason="worker_requested",
            role="worker",
        )
        try:
            from backend.app.platform.inbox.events import notify_inbox_changed

            notify_inbox_changed(company_id, source="voice_call_callback")
        except Exception:
            pass
        try:
            publish_event(
                "voice_call.callback_requested",
                company_id,
                {"callId": ref_id, "workerId": worker_id},
            )
        except Exception:
            pass
        return {"ok": True, "callId": ref_id, "body": body}
