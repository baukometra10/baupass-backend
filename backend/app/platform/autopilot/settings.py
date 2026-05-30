"""Per-company autopilot preferences — reduce manual ops work."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

DEFAULTS: dict[str, Any] = {
    "autoAckInfoAlerts": True,
    "autoAckInfoAlertsAfterHours": 48,
    "autoNotifyDocExpiry": True,
    "autoNotifyDocExpiryDays": 14,
    "autoDailySecurityScan": True,
    "autoSeedAutomationRules": True,
    "autoEnsureScheduledReport": True,
    "scheduledReportLocalHour": 8,
    "scheduledReportTimezone": "Europe/Berlin",
    "autoInboxBulkDocPush": True,
    "autoInboxAckLowSecurity": False,
    "autoPrepareNextMonthDeployment": True,
    "autoSendDeploymentPlans": False,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _table_exists(db) -> bool:
    try:
        db.execute("SELECT 1 FROM company_autopilot_settings LIMIT 1")
        return True
    except Exception:
        return False


def merge_settings(raw: str | None) -> dict[str, Any]:
    out = dict(DEFAULTS)
    if not raw:
        return out
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            out.update({k: v for k, v in data.items() if k in DEFAULTS})
    except json.JSONDecodeError:
        pass
    return out


def get_settings(db, company_id: str) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    if not cid or not _table_exists(db):
        return dict(DEFAULTS)
    row = db.execute(
        "SELECT settings_json, updated_at FROM company_autopilot_settings WHERE company_id = ?",
        (cid,),
    ).fetchone()
    if not row:
        return dict(DEFAULTS)
    merged = merge_settings(row["settings_json"])
    merged["updatedAt"] = row["updated_at"]
    return merged


def save_settings(db, company_id: str, patch: dict[str, Any], *, actor: str | None = None) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    if not cid:
        raise ValueError("company_id_required")
    current = get_settings(db, cid)
    for key in DEFAULTS:
        if key in patch:
            current[key] = patch[key]
    payload = {k: current[k] for k in DEFAULTS}
    db.execute(
        """
        INSERT INTO company_autopilot_settings (company_id, settings_json, updated_at, updated_by)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(company_id) DO UPDATE SET
            settings_json = excluded.settings_json,
            updated_at = excluded.updated_at,
            updated_by = excluded.updated_by
        """,
        (cid, json.dumps(payload), _now_iso(), actor or ""),
    )
    db.commit()
    return get_settings(db, cid)
