"""Short-lived per-company AI operator memory (prefs + last prompts)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

DEFAULTS: dict[str, Any] = {
    "preferredLang": "",
    "preferredSite": "",
    "lastReminderPrompt": "",
    "lastReminderAt": "",
    "recentPrompts": [],  # list[str], max 8
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def ensure_table(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS company_ai_operator_memory (
            company_id TEXT PRIMARY KEY,
            memory_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT
        )
        """
    )


def _merge(raw: str | None) -> dict[str, Any]:
    out = dict(DEFAULTS)
    out["recentPrompts"] = []
    if not raw:
        return out
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return out
        for key in DEFAULTS:
            if key not in data:
                continue
            if key == "recentPrompts":
                items = data.get(key) or []
                if isinstance(items, list):
                    out["recentPrompts"] = [str(x).strip()[:200] for x in items if str(x).strip()][:8]
            else:
                out[key] = str(data.get(key) or "").strip()[:400]
    except json.JSONDecodeError:
        pass
    return out


def get_memory(db, company_id: str) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    if not cid:
        return dict(DEFAULTS) | {"recentPrompts": []}
    try:
        ensure_table(db)
        row = db.execute(
            "SELECT memory_json, updated_at FROM company_ai_operator_memory WHERE company_id = ?",
            (cid,),
        ).fetchone()
    except Exception:
        return dict(DEFAULTS) | {"recentPrompts": []}
    if not row:
        return dict(DEFAULTS) | {"recentPrompts": []}
    mem = _merge(row["memory_json"] if not isinstance(row, tuple) else row[0])
    mem["updatedAt"] = row["updated_at"] if not isinstance(row, tuple) else row[1]
    return mem


def save_memory(
    db,
    company_id: str,
    patch: dict[str, Any],
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    if not cid:
        raise ValueError("company_id_required")
    ensure_table(db)
    current = get_memory(db, cid)
    if "preferredLang" in patch:
        current["preferredLang"] = str(patch.get("preferredLang") or "").strip()[:8]
    if "preferredSite" in patch:
        current["preferredSite"] = str(patch.get("preferredSite") or "").strip()[:120]
    if "lastReminderPrompt" in patch:
        prompt = str(patch.get("lastReminderPrompt") or "").strip()[:400]
        current["lastReminderPrompt"] = prompt
        if prompt:
            current["lastReminderAt"] = _now_iso()
    if "rememberPrompt" in patch:
        prompt = str(patch.get("rememberPrompt") or "").strip()[:200]
        if prompt:
            recent = [prompt] + [p for p in (current.get("recentPrompts") or []) if p != prompt]
            current["recentPrompts"] = recent[:8]
            # Treat reminder-like prompts as last reminder
            low = prompt.lower()
            if any(k in low for k in ("erinner", "remind", "ذكر", "hatırla", "rappel")):
                current["lastReminderPrompt"] = prompt
                current["lastReminderAt"] = _now_iso()
    payload = {k: current[k] for k in DEFAULTS}
    db.execute(
        """
        INSERT INTO company_ai_operator_memory (company_id, memory_json, updated_at, updated_by)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(company_id) DO UPDATE SET
            memory_json = excluded.memory_json,
            updated_at = excluded.updated_at,
            updated_by = excluded.updated_by
        """,
        (cid, json.dumps(payload, ensure_ascii=False), _now_iso(), actor or ""),
    )
    db.commit()
    return get_memory(db, cid)


def memory_context_lines(db, company_id: str, *, lang: str = "de") -> list[str]:
    """Short lines for LLM/context injection."""
    mem = get_memory(db, company_id)
    lines: list[str] = []
    if mem.get("preferredLang"):
        lines.append(f"preferredLang={mem['preferredLang']}")
    if mem.get("preferredSite"):
        lines.append(f"preferredSite={mem['preferredSite']}")
    if mem.get("lastReminderPrompt"):
        lines.append(f"lastReminder={mem['lastReminderPrompt']}")
    recent = mem.get("recentPrompts") or []
    if recent:
        lines.append("recentPrompts=" + " | ".join(recent[:4]))
    return lines
