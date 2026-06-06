"""Persistent AI chat sessions and message history."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def ensure_ai_tables(db) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_chat_sessions (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            agent_id TEXT NOT NULL DEFAULT 'operations',
            title TEXT NOT NULL DEFAULT '',
            lang TEXT NOT NULL DEFAULT 'de',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ai_chat_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            meta_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_sessions_company ON ai_chat_sessions(company_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_ai_sessions_user ON ai_chat_sessions(user_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_ai_messages_session ON ai_chat_messages(session_id, created_at ASC);
        CREATE TABLE IF NOT EXISTS ai_query_audit (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            session_id TEXT,
            agent_id TEXT NOT NULL DEFAULT 'operations',
            mode TEXT NOT NULL DEFAULT 'chat',
            question TEXT NOT NULL,
            tool_calls INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_audit_company ON ai_query_audit(company_id, created_at DESC);
        """
    )
    try:
        db.commit()
    except Exception:
        pass


def create_session(
    db,
    *,
    company_id: str,
    user_id: str,
    agent_id: str = "operations",
    title: str = "",
    lang: str = "de",
) -> dict[str, Any]:
    ensure_ai_tables(db)
    sid = f"ais-{uuid.uuid4().hex[:12]}"
    now = _now()
    title = (title or "").strip() or "Neuer Chat"
    db.execute(
        """
        INSERT INTO ai_chat_sessions (id, company_id, user_id, agent_id, title, lang, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (sid, company_id, user_id, agent_id, title, lang[:2], now, now),
    )
    db.commit()
    return {"id": sid, "companyId": company_id, "agentId": agent_id, "title": title, "lang": lang, "createdAt": now}


def list_sessions(db, *, company_id: str, user_id: str, limit: int = 30) -> list[dict]:
    ensure_ai_tables(db)
    limit = min(50, max(1, limit))
    rows = db.execute(
        """
        SELECT id, company_id, agent_id, title, lang, created_at, updated_at
        FROM ai_chat_sessions
        WHERE company_id = ? AND user_id = ?
        ORDER BY updated_at DESC LIMIT ?
        """,
        (company_id, user_id, limit),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "companyId": r["company_id"],
            "agentId": r["agent_id"],
            "title": r["title"],
            "lang": r["lang"],
            "createdAt": r["created_at"],
            "updatedAt": r["updated_at"],
        }
        for r in rows
    ]


def get_session(db, session_id: str, *, company_id: str, user_id: str) -> dict | None:
    ensure_ai_tables(db)
    row = db.execute(
        """
        SELECT id, company_id, user_id, agent_id, title, lang, created_at, updated_at
        FROM ai_chat_sessions WHERE id = ? AND company_id = ? AND user_id = ?
        """,
        (session_id, company_id, user_id),
    ).fetchone()
    if not row:
        return None
    return dict(row)


def append_message(
    db,
    session_id: str,
    *,
    role: str,
    content: str,
    meta: dict | None = None,
) -> dict[str, Any]:
    ensure_ai_tables(db)
    mid = f"aim-{uuid.uuid4().hex[:12]}"
    now = _now()
    db.execute(
        """
        INSERT INTO ai_chat_messages (id, session_id, role, content, meta_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (mid, session_id, role, content, json.dumps(meta or {}, ensure_ascii=False), now),
    )
    db.execute(
        "UPDATE ai_chat_sessions SET updated_at = ? WHERE id = ?",
        (now, session_id),
    )
    db.commit()
    return {"id": mid, "sessionId": session_id, "role": role, "content": content, "createdAt": now}


def list_messages(db, session_id: str, *, limit: int = 80) -> list[dict]:
    ensure_ai_tables(db)
    limit = min(120, max(1, limit))
    rows = db.execute(
        """
        SELECT id, role, content, meta_json, created_at
        FROM ai_chat_messages WHERE session_id = ?
        ORDER BY created_at ASC LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    out = []
    for r in rows:
        meta = {}
        try:
            meta = json.loads(r["meta_json"] or "{}")
        except Exception:
            pass
        out.append(
            {
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "meta": meta,
                "createdAt": r["created_at"],
            }
        )
    return out


def delete_session(
    db,
    session_id: str,
    *,
    company_id: str,
    user_id: str,
) -> bool:
    ensure_ai_tables(db)
    db.execute(
        "DELETE FROM ai_chat_messages WHERE session_id = ?",
        (session_id,),
    )
    cur = db.execute(
        "DELETE FROM ai_chat_sessions WHERE id = ? AND company_id = ? AND user_id = ?",
        (session_id, company_id, user_id),
    )
    db.commit()
    return int(cur.rowcount or 0) > 0


def delete_all_sessions(db, *, company_id: str, user_id: str) -> int:
    ensure_ai_tables(db)
    rows = db.execute(
        """
        SELECT id FROM ai_chat_sessions
        WHERE company_id = ? AND user_id = ?
        """,
        (company_id, user_id),
    ).fetchall()
    session_ids = [r["id"] for r in rows]
    if not session_ids:
        return 0
    placeholders = ",".join("?" * len(session_ids))
    db.execute(
        f"DELETE FROM ai_chat_messages WHERE session_id IN ({placeholders})",
        tuple(session_ids),
    )
    db.execute(
        "DELETE FROM ai_chat_sessions WHERE company_id = ? AND user_id = ?",
        (company_id, user_id),
    )
    db.commit()
    return len(session_ids)


def touch_session_title(db, session_id: str, title: str) -> None:
    title = (title or "").strip()[:120]
    if not title:
        return
    db.execute(
        "UPDATE ai_chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
        (title, _now(), session_id),
    )
    db.commit()


def record_audit(
    db,
    *,
    company_id: str,
    user_id: str,
    question: str,
    agent_id: str = "operations",
    mode: str = "chat",
    session_id: str | None = None,
    tool_calls: int = 0,
) -> None:
    ensure_ai_tables(db)
    db.execute(
        """
        INSERT INTO ai_query_audit (id, company_id, user_id, session_id, agent_id, mode, question, tool_calls, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"aa-{uuid.uuid4().hex[:12]}",
            company_id,
            user_id,
            session_id,
            agent_id,
            mode,
            question[:2000],
            tool_calls,
            _now(),
        ),
    )
    try:
        db.commit()
    except Exception:
        pass


def audit_stats(db, company_id: str, *, days: int = 7) -> dict[str, Any]:
    ensure_ai_tables(db)
    row = db.execute(
        """
        SELECT COUNT(*) AS c, SUM(tool_calls) AS tools
        FROM ai_query_audit
        WHERE company_id = ? AND created_at >= datetime('now', ?)
        """,
        (company_id, f"-{days} days"),
    ).fetchone()
    by_agent = db.execute(
        """
        SELECT agent_id, COUNT(*) AS c FROM ai_query_audit
        WHERE company_id = ? AND created_at >= datetime('now', ?)
        GROUP BY agent_id
        """,
        (company_id, f"-{days} days"),
    ).fetchall()
    return {
        "queries": int((row["c"] if row else 0) or 0),
        "toolCalls": int((row["tools"] if row else 0) or 0),
        "byAgent": {r["agent_id"]: r["c"] for r in by_agent},
        "days": days,
    }
