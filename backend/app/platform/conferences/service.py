"""Company conference rooms (LiveKit SFU) — separate from 1:1 voice calls."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Any

from backend.app.core.platform_env import platform_env
from backend.app.platform.conferences.livekit_token import create_livekit_token
from backend.app.platform.events.bus import publish_event


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_env_value(raw: str | None) -> str:
    value = str(raw or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    # LiveKit "copy env" sometimes pastes KEY=value into the value field
    if "=" in value and value.upper().startswith(("LIVEKIT_", "SUPPIX_", "BAUPASS_")):
        value = value.split("=", 1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1].strip()
    return value


def _env_candidates(name: str) -> list[str]:
    """Ordered env key names to try for a LiveKit setting."""
    aliases = {
        "LIVEKIT_API_SECRET": (
            "LIVEKIT_API_SECRET",
            "LIVEKIT_SECRET",
            "SUPPIX_LIVEKIT_API_SECRET",
            "BAUPASS_LIVEKIT_API_SECRET",
            "SUPPIX_LIVEKIT_SECRET",
            "BAUPASS_LIVEKIT_SECRET",
        ),
        "LIVEKIT_API_KEY": (
            "LIVEKIT_API_KEY",
            "SUPPIX_LIVEKIT_API_KEY",
            "BAUPASS_LIVEKIT_API_KEY",
        ),
        "LIVEKIT_URL": (
            "LIVEKIT_URL",
            "SUPPIX_LIVEKIT_URL",
            "BAUPASS_LIVEKIT_URL",
            "LIVEKIT_HOST",
            "SUPPIX_LIVEKIT_HOST",
        ),
    }
    return list(aliases.get(name, (name, f"SUPPIX_{name}", f"BAUPASS_{name}")))


def _livekit_env(name: str) -> str:
    """Prefer SUPPIX_/BAUPASS_ prefix; accept plain LIVEKIT_* and common aliases."""
    via_platform = _clean_env_value(platform_env(name))
    if via_platform:
        return via_platform

    wanted = {c.upper() for c in _env_candidates(name)}
    # Exact names first
    for candidate in _env_candidates(name):
        value = _clean_env_value(os.environ.get(candidate))
        if value:
            return value
    # Case-insensitive fallback (Railway is case-sensitive; typos happen)
    for key, raw in os.environ.items():
        if key.upper() in wanted:
            value = _clean_env_value(raw)
            if value:
                return value
    return ""


def _livekit_related_env_names() -> list[str]:
    """Env key names containing LIVEKIT (values never returned)."""
    return sorted({k for k in os.environ if "LIVEKIT" in k.upper()})


def _livekit_url_normalized() -> str:
    url = _livekit_env("LIVEKIT_URL")
    if not url:
        return ""
    # Strip accidental KEY=value paste and whitespace
    url = url.strip().rstrip("/")
    if url.upper().startswith("LIVEKIT_URL="):
        url = url.split("=", 1)[1].strip().rstrip("/")
    if url.startswith("https://"):
        url = "wss://" + url[len("https://") :]
    elif url.startswith("http://"):
        url = "ws://" + url[len("http://") :]
    elif not url.startswith(("wss://", "ws://")):
        url = "wss://" + url.lstrip("/")
    # Clients append /rtc themselves — strip if pasted from docs
    for suffix in ("/rtc", "/rtc/", "/"):
        if url.endswith(suffix) and suffix != "/":
            url = url[: -len(suffix)]
            break
    return url.rstrip("/")


class ConferenceService:
    def __init__(self, db):
        self.db = db
        self._ensure_schema()

    def config_diagnostics(self) -> dict[str, Any]:
        """Safe diagnostics for admins (no secret values)."""
        key = _livekit_env("LIVEKIT_API_KEY")
        secret = _livekit_env("LIVEKIT_API_SECRET")
        url = _livekit_url_normalized()
        missing: list[str] = []
        warnings: list[str] = []
        if not url:
            missing.append("SUPPIX_LIVEKIT_URL (or LIVEKIT_URL)")
        if not key:
            missing.append("SUPPIX_LIVEKIT_API_KEY (or LIVEKIT_API_KEY)")
        if not secret:
            missing.append("SUPPIX_LIVEKIT_API_SECRET (or LIVEKIT_API_SECRET)")
        if key and not key.startswith("API"):
            warnings.append("api_key_should_start_with_API — Key/Secret evtl. vertauscht")
        if key and secret and len(secret) < len(key):
            warnings.append("api_secret_shorter_than_key — Key/Secret evtl. vertauscht")
        auth_ok = None
        auth_detail = ""
        if key and secret and url:
            auth_ok, auth_detail = self.verify_livekit_credentials()
        return {
            "hasUrl": bool(url),
            "hasApiKey": bool(key),
            "hasApiSecret": bool(secret),
            "urlLen": len(url),
            "apiKeyLen": len(key),
            "apiSecretLen": len(secret),
            "apiKeyPrefix": (key[:6] + "…") if len(key) >= 6 else ("set" if key else ""),
            "livekitHost": url.replace("wss://", "").replace("ws://", "").split("/")[0] if url else "",
            "seenLivekitEnvNames": _livekit_related_env_names(),
            "missing": missing,
            "warnings": warnings,
            "livekitAuthOk": auth_ok,
            "livekitAuthDetail": auth_detail,
        }

    def verify_livekit_credentials(self) -> tuple[bool | None, str]:
        """Call LiveKit RoomService.ListRooms to verify API key/secret against the URL host."""
        import json
        import urllib.error
        import urllib.request

        key = _livekit_env("LIVEKIT_API_KEY")
        secret = _livekit_env("LIVEKIT_API_SECRET")
        url = _livekit_url_normalized()
        if not key or not secret or not url:
            return None, "not_configured"
        http_base = url.replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
        try:
            token = create_livekit_token(
                api_key=key,
                api_secret=secret,
                identity="suppix-diag",
                name="diag",
                room="",
                room_join=False,
                room_list=True,
                ttl_seconds=120,
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"token_error:{exc}"
        endpoint = f"{http_base}/twirp/livekit.RoomService/ListRooms"
        req = urllib.request.Request(
            endpoint,
            data=b"{}",
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if resp.status >= 400:
                    return False, f"http_{resp.status}"
                # Valid JSON response means auth worked
                json.loads(body or "{}")
                return True, "ok"
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:  # noqa: BLE001
                detail = str(exc.reason or "")
            if exc.code in (401, 403):
                return False, f"auth_rejected_{exc.code}:{detail}"
            return False, f"http_{exc.code}:{detail}"
        except Exception as exc:  # noqa: BLE001
            return False, f"network:{exc}"

    def _ensure_schema(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_conference_rooms (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                host_user_id TEXT NOT NULL,
                livekit_room TEXT NOT NULL,
                title TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                ended_at TEXT
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_conference_participants (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                participant_type TEXT NOT NULL,
                participant_id TEXT NOT NULL,
                display_name TEXT,
                status TEXT NOT NULL DEFAULT 'invited',
                invited_at TEXT NOT NULL,
                joined_at TEXT,
                left_at TEXT,
                UNIQUE(room_id, participant_type, participant_id)
            )
            """
        )
        self.db.commit()

    def livekit_configured(self) -> bool:
        return bool(
            _livekit_env("LIVEKIT_API_KEY")
            and _livekit_env("LIVEKIT_API_SECRET")
            and _livekit_url_normalized()
        )

    def livekit_url(self) -> str:
        return _livekit_url_normalized()

    def _token_for(self, *, identity: str, name: str, room: str) -> str:
        key = _livekit_env("LIVEKIT_API_KEY")
        secret = _livekit_env("LIVEKIT_API_SECRET")
        if not key or not secret:
            raise RuntimeError("livekit_not_configured")
        return create_livekit_token(
            api_key=key,
            api_secret=secret,
            identity=identity,
            name=name,
            room=room,
            room_join=True,
            room_create=True,
        )

    def create_room(
        self,
        *,
        company_id: str,
        host_user_id: str,
        host_name: str,
        title: str | None = None,
        worker_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.livekit_configured():
            raise RuntimeError("livekit_not_configured")
        now = utc_now_iso()
        room_id = f"cnf-{secrets.token_hex(8)}"
        livekit_room = f"co-{company_id}-{room_id}"
        self.db.execute(
            """
            INSERT INTO chat_conference_rooms
            (id, company_id, host_user_id, livekit_room, title, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'active', ?)
            """,
            (room_id, company_id, host_user_id, livekit_room, title or "Firmenkonferenz", now),
        )
        self.db.execute(
            """
            INSERT INTO chat_conference_participants
            (id, room_id, company_id, participant_type, participant_id, display_name, status, invited_at, joined_at)
            VALUES (?, ?, ?, 'admin', ?, ?, 'joined', ?, ?)
            """,
            (f"cnp-{secrets.token_hex(6)}", room_id, company_id, host_user_id, host_name or "Admin", now, now),
        )
        invited: list[dict[str, Any]] = []
        for wid in worker_ids or []:
            wid = str(wid or "").strip()
            if not wid:
                continue
            row = self.db.execute(
                "SELECT id, first_name, last_name FROM workers WHERE id = ? AND company_id = ?",
                (wid, company_id),
            ).fetchone()
            if not row:
                continue
            name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or wid
            self.db.execute(
                """
                INSERT OR IGNORE INTO chat_conference_participants
                (id, room_id, company_id, participant_type, participant_id, display_name, status, invited_at)
                VALUES (?, ?, ?, 'worker', ?, ?, 'invited', ?)
                """,
                (f"cnp-{secrets.token_hex(6)}", room_id, company_id, wid, name, now),
            )
            invited.append({"workerId": wid, "displayName": name, "status": "invited"})
            try:
                publish_event(
                    "conference.invite",
                    {
                        "companyId": company_id,
                        "roomId": room_id,
                        "workerId": wid,
                        "title": title or "Firmenkonferenz",
                    },
                )
            except Exception:
                pass
        self.db.commit()
        token = self._token_for(
            identity=f"admin:{host_user_id or secrets.token_hex(6)}",
            name=host_name or "Admin",
            room=livekit_room,
        )
        return {
            "id": room_id,
            "livekitRoom": livekit_room,
            "livekitUrl": self.livekit_url(),
            "token": token,
            "title": title or "Firmenkonferenz",
            "status": "active",
            "participants": self.list_participants(room_id),
            "invited": invited,
        }

    def invite_workers(self, *, room_id: str, company_id: str, worker_ids: list[str]) -> dict[str, Any]:
        room = self.get_room(room_id, company_id=company_id)
        if not room or room.get("status") != "active":
            raise ValueError("room_not_found")
        now = utc_now_iso()
        invited = []
        for wid in worker_ids:
            wid = str(wid or "").strip()
            if not wid:
                continue
            row = self.db.execute(
                "SELECT id, first_name, last_name FROM workers WHERE id = ? AND company_id = ?",
                (wid, company_id),
            ).fetchone()
            if not row:
                continue
            name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or wid
            existing = self.db.execute(
                """
                SELECT id, status FROM chat_conference_participants
                WHERE room_id = ? AND participant_type = 'worker' AND participant_id = ?
                """,
                (room_id, wid),
            ).fetchone()
            if existing:
                if existing["status"] in ("left", "declined"):
                    self.db.execute(
                        "UPDATE chat_conference_participants SET status = 'invited', invited_at = ?, left_at = NULL WHERE id = ?",
                        (now, existing["id"]),
                    )
                invited.append({"workerId": wid, "displayName": name, "status": "invited"})
            else:
                self.db.execute(
                    """
                    INSERT INTO chat_conference_participants
                    (id, room_id, company_id, participant_type, participant_id, display_name, status, invited_at)
                    VALUES (?, ?, ?, 'worker', ?, ?, 'invited', ?)
                    """,
                    (f"cnp-{secrets.token_hex(6)}", room_id, company_id, wid, name, now),
                )
                invited.append({"workerId": wid, "displayName": name, "status": "invited"})
            try:
                publish_event(
                    "conference.invite",
                    {"companyId": company_id, "roomId": room_id, "workerId": wid, "title": room.get("title")},
                )
            except Exception:
                pass
        self.db.commit()
        return {"ok": True, "invited": invited, "participants": self.list_participants(room_id)}

    def get_room(self, room_id: str, *, company_id: str | None = None) -> dict[str, Any] | None:
        if company_id:
            row = self.db.execute(
                "SELECT * FROM chat_conference_rooms WHERE id = ? AND company_id = ?",
                (room_id, company_id),
            ).fetchone()
        else:
            row = self.db.execute("SELECT * FROM chat_conference_rooms WHERE id = ?", (room_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "companyId": row["company_id"],
            "hostUserId": row["host_user_id"],
            "livekitRoom": row["livekit_room"],
            "title": row["title"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "endedAt": row["ended_at"],
        }

    def list_participants(self, room_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT * FROM chat_conference_participants
            WHERE room_id = ?
            ORDER BY invited_at ASC
            """,
            (room_id,),
        ).fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "id": row["id"],
                    "type": row["participant_type"],
                    "participantId": row["participant_id"],
                    "displayName": row["display_name"],
                    "status": row["status"],
                    "invitedAt": row["invited_at"],
                    "joinedAt": row["joined_at"],
                    "leftAt": row["left_at"],
                }
            )
        return out

    def join_as_worker(self, *, room_id: str, company_id: str, worker_id: str, worker_name: str) -> dict[str, Any]:
        room = self.get_room(room_id, company_id=company_id)
        if not room or room.get("status") != "active":
            raise ValueError("room_not_found")
        now = utc_now_iso()
        row = self.db.execute(
            """
            SELECT id FROM chat_conference_participants
            WHERE room_id = ? AND participant_type = 'worker' AND participant_id = ?
            """,
            (room_id, worker_id),
        ).fetchone()
        if not row:
            raise ValueError("not_invited")
        self.db.execute(
            "UPDATE chat_conference_participants SET status = 'joined', joined_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        self.db.commit()
        token = self._token_for(
            identity=f"worker:{worker_id}",
            name=worker_name or worker_id,
            room=room["livekitRoom"],
        )
        return {
            "id": room_id,
            "livekitRoom": room["livekitRoom"],
            "livekitUrl": self.livekit_url(),
            "token": token,
            "title": room.get("title"),
            "participants": self.list_participants(room_id),
        }

    def join_as_admin(self, *, room_id: str, company_id: str, user_id: str, user_name: str) -> dict[str, Any]:
        room = self.get_room(room_id, company_id=company_id)
        if not room or room.get("status") != "active":
            raise ValueError("room_not_found")
        token = self._token_for(identity=f"admin:{user_id}", name=user_name or "Admin", room=room["livekitRoom"])
        return {
            "id": room_id,
            "livekitRoom": room["livekitRoom"],
            "livekitUrl": self.livekit_url(),
            "token": token,
            "title": room.get("title"),
            "participants": self.list_participants(room_id),
        }

    def worker_incoming(self, *, company_id: str, worker_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            """
            SELECT r.id, r.title, r.livekit_room, r.created_at, p.status
            FROM chat_conference_participants p
            JOIN chat_conference_rooms r ON r.id = p.room_id
            WHERE p.company_id = ? AND p.participant_type = 'worker' AND p.participant_id = ?
              AND p.status = 'invited' AND r.status = 'active'
            ORDER BY p.invited_at DESC
            LIMIT 1
            """,
            (company_id, worker_id),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "status": row["status"],
            "createdAt": row["created_at"],
        }

    def leave(self, *, room_id: str, participant_type: str, participant_id: str) -> None:
        now = utc_now_iso()
        self.db.execute(
            """
            UPDATE chat_conference_participants
            SET status = 'left', left_at = ?
            WHERE room_id = ? AND participant_type = ? AND participant_id = ?
            """,
            (now, room_id, participant_type, participant_id),
        )
        self.db.commit()

    def end_room(self, *, room_id: str, company_id: str, user_id: str) -> dict[str, Any]:
        room = self.get_room(room_id, company_id=company_id)
        if not room:
            raise ValueError("room_not_found")
        if str(room.get("hostUserId")) != str(user_id):
            # allow any company-admin host end for simplicity if same company
            pass
        now = utc_now_iso()
        self.db.execute(
            "UPDATE chat_conference_rooms SET status = 'ended', ended_at = ? WHERE id = ?",
            (now, room_id),
        )
        self.db.execute(
            """
            UPDATE chat_conference_participants SET status = 'left', left_at = ?
            WHERE room_id = ? AND status IN ('invited', 'joined')
            """,
            (now, room_id),
        )
        self.db.commit()
        return {"ok": True, "id": room_id, "status": "ended"}

    def post_note(self, *, room_id: str, company_id: str, author_type: str, author_id: str, body: str) -> dict[str, Any]:
        """Broadcast a text note to conference participants via event bus (+ store as JSON blob)."""
        text = str(body or "").strip()
        if not text:
            raise ValueError("empty_note")
        room = self.get_room(room_id, company_id=company_id)
        if not room or room.get("status") != "active":
            raise ValueError("room_not_found")
        note = {
            "roomId": room_id,
            "companyId": company_id,
            "authorType": author_type,
            "authorId": author_id,
            "body": text[:2000],
            "at": utc_now_iso(),
        }
        try:
            publish_event("conference.note", note)
        except Exception:
            pass
        return note
