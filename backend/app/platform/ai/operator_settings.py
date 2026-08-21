"""Per-company AI Operator FAB visibility / voice / briefing prefs."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "voiceEnabled": True,
    "welcomeEnabled": False,
    # Morning pulse dispatch (Slack/email) — per company schedule
    "briefingEnabled": True,
    # auto = from company work_start + shift starts; manual = briefingHours list
    "briefingHoursMode": "auto",
    "briefingHours": [],  # only used when mode=manual
    "briefingTz": "",  # empty → company report_timezone → env → Europe/Berlin
    "briefingLang": "",  # empty/auto → company invoice_email_lang → env → de
    "briefingEmail": "",  # optional override; empty → company admins/billing → env
}

_AUTO_TOKENS = frozenset({"", "auto", "automatic", "automatisch", "*"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def ensure_table(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS company_ai_operator_settings (
            company_id TEXT PRIMARY KEY,
            settings_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS company_ai_briefing_sends (
            company_id TEXT NOT NULL,
            send_date TEXT NOT NULL,
            send_hour INTEGER NOT NULL,
            sent_at TEXT NOT NULL,
            PRIMARY KEY (company_id, send_date, send_hour)
        )
        """
    )


def is_auto_briefing_hours(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return True
    if isinstance(value, str) and value.strip().lower() in _AUTO_TOKENS:
        return True
    return False


def normalize_briefing_hours(value: Any, *, allow_empty: bool = False) -> list[int]:
    """Parse hours from list / CSV / single int → unique sorted 0..23."""
    if is_auto_briefing_hours(value):
        return [] if allow_empty else default_briefing_hours_from_env()
    hours: list[int] = []
    if isinstance(value, int):
        hours = [value]
    elif isinstance(value, float):
        hours = [int(value)]
    elif isinstance(value, str):
        parts = re.split(r"[,;\s]+", value.strip())
        for part in parts:
            if not part or part.lower() in _AUTO_TOKENS:
                continue
            part = part.split(":", 1)[0]
            try:
                hours.append(int(part))
            except ValueError:
                continue
    elif isinstance(value, (list, tuple)):
        for item in value:
            try:
                if isinstance(item, str) and ":" in item:
                    item = item.split(":", 1)[0]
                hours.append(int(item))
            except (TypeError, ValueError):
                continue
    out = sorted({h for h in hours if 0 <= h <= 23})
    if out:
        return out
    return [] if allow_empty else default_briefing_hours_from_env()


def normalize_briefing_hours_mode(value: Any) -> str:
    raw = str(value or "auto").strip().lower()
    if raw in {"manual", "fixed", "custom", "fest"}:
        return "manual"
    return "auto"


def default_briefing_hours_from_env() -> list[int]:
    raw = os.getenv("BAUPASS_AI_BRIEFING_HOUR", "7")
    if is_auto_briefing_hours(raw):
        return [7]
    hours = normalize_briefing_hours(raw, allow_empty=True)
    return hours or [7]


def _hour_from_time_text(raw: str) -> int | None:
    text = str(raw or "").strip()
    if not text:
        return None
    # ISO datetime → take hour
    if "T" in text and len(text) >= 13:
        try:
            # 2026-07-25T06:30:00 or with Z
            hh = text.split("T", 1)[1][:2]
            h = int(hh)
            if 0 <= h <= 23:
                return h
        except ValueError:
            pass
    # HH:MM / HH:MM:SS
    if ":" in text:
        try:
            h = int(text.split(":", 1)[0])
            if 0 <= h <= 23:
                return h
        except ValueError:
            return None
    try:
        h = int(text)
        if 0 <= h <= 23:
            return h
    except ValueError:
        return None
    return None


def _briefing_hour_before_start(start_hour: int) -> int:
    """Pulse one hour before shift/work start (ops prep)."""
    return max(0, int(start_hour) - 1)


def auto_briefing_hours_for_company(db, company_id: str) -> list[int]:
    """
    Derive local briefing hours from company work_start + upcoming shift starts.
    Briefing fires 1h before each distinct start hour.
    """
    cid = str(company_id or "").strip()
    found: set[int] = set()
    if not cid or db is None:
        return default_briefing_hours_from_env()

    try:
        row = db.execute(
            "SELECT work_start_time FROM companies WHERE id = ?",
            (cid,),
        ).fetchone()
        raw = ""
        if row is not None:
            raw = str(row["work_start_time"] if not isinstance(row, tuple) else row[0] or "").strip()
        start_h = _hour_from_time_text(raw)
        if start_h is not None:
            found.add(_briefing_hour_before_start(start_h))
    except Exception:
        pass

    try:
        now = datetime.now(timezone.utc)
        until = (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        since = (now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = db.execute(
            """
            SELECT start_time FROM shift_assignments
            WHERE company_id = ?
              AND COALESCE(status, '') NOT IN ('cancelled', 'canceled', 'deleted')
              AND start_time >= ? AND start_time <= ?
            LIMIT 200
            """,
            (cid, since, until),
        ).fetchall()
        for r in rows or []:
            st = r["start_time"] if not isinstance(r, tuple) else r[0]
            h = _hour_from_time_text(str(st or ""))
            if h is not None:
                found.add(_briefing_hour_before_start(h))
    except Exception:
        pass

    if found:
        return sorted(found)
    return default_briefing_hours_from_env()


def resolve_effective_briefing_hours(
    settings: dict[str, Any] | None,
    *,
    db=None,
    company_id: str | None = None,
) -> list[int]:
    s = settings or {}
    mode = normalize_briefing_hours_mode(s.get("briefingHoursMode"))
    if mode == "manual":
        hours = normalize_briefing_hours(s.get("briefingHours"), allow_empty=True)
        return hours or default_briefing_hours_from_env()
    return auto_briefing_hours_for_company(db, company_id or "")


def _coerce_setting(key: str, val: Any) -> Any:
    default = DEFAULTS[key]
    if isinstance(default, bool):
        if isinstance(val, str):
            return val.strip().lower() not in {"0", "false", "no", "off"}
        return bool(val)
    if key == "briefingHoursMode":
        return normalize_briefing_hours_mode(val)
    if key == "briefingHours":
        return normalize_briefing_hours(val, allow_empty=True)
    if isinstance(default, list):
        return list(val) if isinstance(val, (list, tuple)) else default
    if isinstance(default, str):
        return str(val or "").strip()
    return val


def merge_settings(raw: str | None) -> dict[str, Any]:
    out = dict(DEFAULTS)
    out["briefingHours"] = list(DEFAULTS["briefingHours"])
    if not raw:
        return out
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            for key in DEFAULTS:
                if key in data:
                    out[key] = _coerce_setting(key, data[key])
            # legacy single hour → treat as manual
            if "briefingHour" in data and "briefingHours" not in data and "briefingHoursMode" not in data:
                out["briefingHours"] = normalize_briefing_hours(data.get("briefingHour"), allow_empty=True)
                out["briefingHoursMode"] = "manual" if out["briefingHours"] else "auto"
            # old saves with only briefingHours list and no mode → manual if non-empty
            if "briefingHoursMode" not in data and data.get("briefingHours") not in (None, "", []):
                if not is_auto_briefing_hours(data.get("briefingHours")):
                    out["briefingHoursMode"] = "manual"
    except json.JSONDecodeError:
        pass
    return out


def get_settings(db, company_id: str) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    if not cid:
        return dict(DEFAULTS) | {"briefingHours": list(DEFAULTS["briefingHours"])}
    try:
        ensure_table(db)
        row = db.execute(
            "SELECT settings_json, updated_at FROM company_ai_operator_settings WHERE company_id = ?",
            (cid,),
        ).fetchone()
    except Exception:
        return dict(DEFAULTS) | {"briefingHours": list(DEFAULTS["briefingHours"])}
    if not row:
        return dict(DEFAULTS) | {"briefingHours": list(DEFAULTS["briefingHours"])}
    merged = merge_settings(row["settings_json"] if not isinstance(row, tuple) else row[0])
    updated = row["updated_at"] if not isinstance(row, tuple) else row[1]
    merged["updatedAt"] = updated
    return merged


def enrich_settings_for_api(db, company_id: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach resolved hours/tz/email for admin UI (mode=auto preview)."""
    s = dict(settings or get_settings(db, company_id))
    s["briefingHoursResolved"] = resolve_effective_briefing_hours(s, db=db, company_id=company_id)
    s["briefingTzResolved"] = resolve_briefing_tz(s, db=db, company_id=company_id)
    s["briefingEmailResolved"] = resolve_briefing_email(s, db=db, company_id=company_id)
    s["briefingLangResolved"] = resolve_briefing_lang(s, db=db, company_id=company_id)
    return s


def save_settings(db, company_id: str, patch: dict[str, Any], *, actor: str | None = None) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    if not cid:
        raise ValueError("company_id_required")
    ensure_table(db)
    current = get_settings(db, cid)

    # Hours field: "auto"/empty → auto mode; CSV → manual
    if "briefingHours" in patch and "briefingHoursMode" not in patch:
        if is_auto_briefing_hours(patch.get("briefingHours")):
            current["briefingHoursMode"] = "auto"
            current["briefingHours"] = []
        else:
            current["briefingHoursMode"] = "manual"
            current["briefingHours"] = normalize_briefing_hours(patch.get("briefingHours"), allow_empty=True)

    for key in DEFAULTS:
        if key in patch and not (key == "briefingHours" and "briefingHours" in patch and "briefingHoursMode" not in patch):
            # briefingHours already handled above when mode inferred
            if key == "briefingHours" and "briefingHoursMode" not in patch:
                continue
            current[key] = _coerce_setting(key, patch[key])

    if "briefingHour" in patch and "briefingHours" not in patch:
        current["briefingHours"] = normalize_briefing_hours(patch.get("briefingHour"), allow_empty=True)
        current["briefingHoursMode"] = "manual" if current["briefingHours"] else "auto"

    if current.get("briefingHoursMode") == "auto":
        current["briefingHours"] = []

    payload = {k: current[k] for k in DEFAULTS}
    db.execute(
        """
        INSERT INTO company_ai_operator_settings (company_id, settings_json, updated_at, updated_by)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(company_id) DO UPDATE SET
            settings_json = excluded.settings_json,
            updated_at = excluded.updated_at,
            updated_by = excluded.updated_by
        """,
        (cid, json.dumps(payload), _now_iso(), actor or ""),
    )
    db.commit()
    return enrich_settings_for_api(db, cid, get_settings(db, cid))


def resolve_briefing_tz(
    settings: dict[str, Any] | None = None,
    *,
    db=None,
    company_id: str | None = None,
) -> str:
    raw = str((settings or {}).get("briefingTz") or "").strip()
    if raw and raw.lower() not in {"auto", "automatic", "automatisch", "*"}:
        return raw
    cid = str(company_id or "").strip()
    if db is not None and cid:
        try:
            row = db.execute(
                "SELECT report_timezone FROM companies WHERE id = ?",
                (cid,),
            ).fetchone()
            if row is not None:
                tz = str(row["report_timezone"] if not isinstance(row, tuple) else row[0] or "").strip()
                if tz and tz.lower() not in {"auto", "automatic", "automatisch", "*"}:
                    return tz
        except Exception:
            pass
    env_tz = (os.getenv("BAUPASS_AI_BRIEFING_TZ") or "").strip()
    if env_tz and env_tz.lower() not in {"auto", "automatic", "automatisch", "*"}:
        return env_tz
    return "Europe/Berlin"


def lookup_company_briefing_lang(db, company_id: str) -> str:
    """Company mail/UI language (invoice_email_lang) — all 8 system langs."""
    from .langs import try_normalize_ui_lang

    cid = str(company_id or "").strip()
    if not cid or db is None:
        return ""
    try:
        row = db.execute(
            "SELECT invoice_email_lang FROM companies WHERE id = ?",
            (cid,),
        ).fetchone()
        if row is not None:
            raw = row["invoice_email_lang"] if not isinstance(row, tuple) else row[0]
            hit = try_normalize_ui_lang(str(raw or ""))
            if hit:
                return hit
    except Exception:
        pass
    return ""


def resolve_briefing_lang(
    settings: dict[str, Any] | None = None,
    *,
    db=None,
    company_id: str | None = None,
) -> str:
    """
    Briefing language per company:
    override → company invoice_email_lang → env (if not auto) → de
    """
    from .langs import normalize_ui_lang, try_normalize_ui_lang

    raw = str((settings or {}).get("briefingLang") or "").strip()
    if raw and raw.lower() not in {"auto", "automatic", "automatisch", "*"}:
        hit = try_normalize_ui_lang(raw)
        if hit:
            return hit
    company_lang = lookup_company_briefing_lang(db, company_id or "")
    if company_lang:
        return company_lang
    # Operator memory preferred language (learned from FAB usage)
    if db is not None and company_id:
        try:
            from .operator_memory import get_memory

            pref = str(get_memory(db, company_id).get("preferredLang") or "").strip()
            hit = try_normalize_ui_lang(pref)
            if hit:
                return hit
        except Exception:
            pass
    env_raw = str(os.getenv("BAUPASS_AI_BRIEFING_LANG") or "").strip()
    if env_raw and env_raw.lower() not in {"auto", "automatic", "automatisch", "*"}:
        hit = try_normalize_ui_lang(env_raw)
        if hit:
            return hit
    return normalize_ui_lang("de")


def _looks_like_email(value: str) -> bool:
    text = str(value or "").strip()
    if "@" not in text or " " in text:
        return False
    local, _, domain = text.partition("@")
    return bool(local) and "." in domain


def lookup_company_briefing_emails(db, company_id: str) -> list[str]:
    """
    Multi-company default recipients for ops pulse:
    1) all company-admin user emails (preferred)
    2) else company billing_email / document_email / contract_owner_email
    """
    cid = str(company_id or "").strip()
    if not cid or db is None:
        return []
    found: list[str] = []
    seen: set[str] = set()

    def _add(raw: Any) -> None:
        email = str(raw or "").strip()
        key = email.lower()
        if not _looks_like_email(email) or key in seen:
            return
        seen.add(key)
        found.append(email)

    try:
        rows = db.execute(
            """
            SELECT email FROM users
            WHERE company_id = ?
              AND role = 'company-admin'
              AND COALESCE(is_active, 1) = 1
              AND COALESCE(email, '') <> ''
            """,
            (cid,),
        ).fetchall()
        for row in rows or []:
            _add(row["email"] if not isinstance(row, tuple) else row[0])
    except Exception:
        # older schemas may lack is_active
        try:
            rows = db.execute(
                """
                SELECT email FROM users
                WHERE company_id = ? AND role = 'company-admin' AND COALESCE(email, '') <> ''
                """,
                (cid,),
            ).fetchall()
            for row in rows or []:
                _add(row["email"] if not isinstance(row, tuple) else row[0])
        except Exception:
            pass

    if found:
        return found

    try:
        row = db.execute(
            """
            SELECT billing_email, document_email, contract_owner_email, contact
            FROM companies WHERE id = ?
            """,
            (cid,),
        ).fetchone()
        if row is not None:
            if isinstance(row, tuple):
                for val in row:
                    _add(val)
            else:
                for key in ("billing_email", "document_email", "contract_owner_email", "contact"):
                    try:
                        _add(row[key])
                    except Exception:
                        pass
    except Exception:
        try:
            row = db.execute(
                "SELECT billing_email FROM companies WHERE id = ?",
                (cid,),
            ).fetchone()
            if row is not None:
                _add(row["billing_email"] if not isinstance(row, tuple) else row[0])
        except Exception:
            pass

    return found


def resolve_briefing_email(
    settings: dict[str, Any] | None = None,
    *,
    db=None,
    company_id: str | None = None,
) -> str:
    """
    Recipient for company pulse email.
    Override (settings/env) → company admins/billing → global env fallback.
    """
    raw = str((settings or {}).get("briefingEmail") or "").strip()
    if raw and raw.lower() not in {"auto", "automatic", "automatisch"}:
        return raw
    company_emails = lookup_company_briefing_emails(db, company_id or "")
    if company_emails:
        # primary To = first; extras as comma-list (SMTP To accepts it)
        return ", ".join(company_emails)
    env_email = (os.getenv("BAUPASS_AI_BRIEFING_EMAIL") or "").strip()
    if env_email.lower() in {"auto", "automatic", "automatisch", "*"}:
        return ""
    return env_email


def briefing_already_sent(db, company_id: str, *, send_date: str, send_hour: int) -> bool:
    try:
        ensure_table(db)
        row = db.execute(
            """
            SELECT 1 FROM company_ai_briefing_sends
            WHERE company_id = ? AND send_date = ? AND send_hour = ?
            """,
            (company_id, send_date, int(send_hour)),
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def mark_briefing_sent(db, company_id: str, *, send_date: str, send_hour: int) -> None:
    ensure_table(db)
    db.execute(
        """
        INSERT INTO company_ai_briefing_sends (company_id, send_date, send_hour, sent_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(company_id, send_date, send_hour) DO UPDATE SET sent_at = excluded.sent_at
        """,
        (company_id, send_date, int(send_hour), _now_iso()),
    )
    db.commit()
