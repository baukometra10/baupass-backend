"""Camera night-watch: business hours, after-hours detection, watch settings."""
from __future__ import annotations

import json
import os
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ._common import now_iso

DEFAULT_TZ = "Europe/Berlin"
DEFAULT_WORK_START = "06:00"
DEFAULT_WORK_END = "18:00"
DEFAULT_WORK_DAYS = "1,2,3,4,5"  # Mon–Fri (ISO weekday)
DEFAULT_ESCALATE_AFTER_MINUTES = 15
DEFAULT_NOTIFY_RULES: dict[str, Any] = {
    "sms": "critical",
    "push": "high",
    "email": "immediate",
}
OVERRIDE_KINDS = frozenset({"holiday", "special_hours", "force_watch", "force_open", "force_after_hours"})


def _parse_hhmm(value: str, fallback: str) -> time:
    raw = str(value or fallback).strip() or fallback
    try:
        parts = raw.split(":")
        return time(hour=int(parts[0]), minute=int(parts[1]) if len(parts) > 1 else 0)
    except Exception:
        fb = fallback.split(":")
        return time(hour=int(fb[0]), minute=int(fb[1]) if len(fb) > 1 else 0)


def _parse_days(raw: str) -> set[int]:
    out: set[int] = set()
    for part in str(raw or DEFAULT_WORK_DAYS).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            d = int(part)
            if 1 <= d <= 7:
                out.add(d)
        except Exception:
            continue
    return out or {1, 2, 3, 4, 5}


def _row_has(row, key: str) -> bool:
    try:
        return key in row.keys()
    except Exception:
        return False


def _row_get(row, key: str, default: Any = None) -> Any:
    if row is None or not _row_has(row, key):
        return default
    try:
        return row[key]
    except Exception:
        return default


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_escalate_minutes(value: Any, default: int = DEFAULT_ESCALATE_AFTER_MINUTES) -> int:
    try:
        mins = int(value)
        return max(1, min(24 * 60, mins))
    except Exception:
        return default


def _parse_notify_rules(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        merged = {**DEFAULT_NOTIFY_RULES, **raw}
        return merged
    try:
        data = json.loads(raw or "{}")
        if isinstance(data, dict):
            return {**DEFAULT_NOTIFY_RULES, **data}
    except Exception:
        pass
    return dict(DEFAULT_NOTIFY_RULES)


def _notify_rules_json(rules: dict[str, Any] | None) -> str:
    return json.dumps(rules if isinstance(rules, dict) else DEFAULT_NOTIFY_RULES, ensure_ascii=False)


def default_watch_settings(company_id: str) -> dict[str, Any]:
    return {
        "companyId": str(company_id),
        "enabled": True,
        "timezone": os.getenv("BAUPASS_CAMERA_WATCH_TZ", DEFAULT_TZ),
        "workStart": DEFAULT_WORK_START,
        "workEnd": DEFAULT_WORK_END,
        "workDays": DEFAULT_WORK_DAYS,
        "country": "",
        "city": "",
        "latitude": None,
        "longitude": None,
        "securityWebhookUrl": "",
        "escalateAfterMinutes": DEFAULT_ESCALATE_AFTER_MINUTES,
        "escalateSecondContact": "",
        "requireDualAck": True,
        "notifyRules": dict(DEFAULT_NOTIFY_RULES),
        "updatedAt": None,
    }


def get_watch_settings(db, company_id: str) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    base = default_watch_settings(cid)
    if not cid:
        return base
    try:
        row = db.execute(
            "SELECT * FROM camera_watch_settings WHERE company_id = ?",
            (cid,),
        ).fetchone()
    except Exception:
        return base
    if not row:
        return base
    return {
        "companyId": cid,
        "enabled": bool(int(row["enabled"] or 0)),
        "timezone": str(row["timezone"] or DEFAULT_TZ),
        "workStart": str(row["work_start"] or DEFAULT_WORK_START),
        "workEnd": str(row["work_end"] or DEFAULT_WORK_END),
        "workDays": str(row["work_days"] or DEFAULT_WORK_DAYS),
        "country": str(row["country"] or ""),
        "city": str(row["city"] or ""),
        "latitude": float(row["latitude"]) if row["latitude"] is not None else None,
        "longitude": float(row["longitude"]) if row["longitude"] is not None else None,
        "securityWebhookUrl": str(row["security_webhook_url"] or ""),
        "escalateAfterMinutes": _parse_escalate_minutes(
            _row_get(row, "escalate_after_minutes", DEFAULT_ESCALATE_AFTER_MINUTES)
        ),
        "escalateSecondContact": str(_row_get(row, "escalate_second_contact", "") or ""),
        "requireDualAck": _parse_bool(_row_get(row, "require_dual_ack", 1), True),
        "notifyRules": _parse_notify_rules(_row_get(row, "notify_rules_json", "{}")),
        "updatedAt": str(row["updated_at"] or "") or None,
    }


def upsert_watch_settings(db, company_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    if not cid:
        raise ValueError("company_id_required")
    data = payload or {}
    cur = get_watch_settings(db, cid)
    enabled = data.get("enabled")
    if enabled is None:
        enabled = cur["enabled"]
    else:
        enabled = _parse_bool(enabled, True)
    tz = str(data.get("timezone") or data.get("tz") or cur["timezone"] or DEFAULT_TZ).strip() or DEFAULT_TZ
    work_start = str(data.get("workStart") or data.get("work_start") or cur["workStart"]).strip()
    work_end = str(data.get("workEnd") or data.get("work_end") or cur["workEnd"]).strip()
    work_days = str(data.get("workDays") or data.get("work_days") or cur["workDays"]).strip()
    country = str(data.get("country") or cur["country"] or "").strip()[:80]
    city = str(data.get("city") or cur["city"] or "").strip()[:120]
    lat = data.get("latitude", cur["latitude"])
    lng = data.get("longitude", cur["longitude"])
    try:
        lat_f = float(lat) if lat is not None and str(lat).strip() != "" else None
    except Exception:
        lat_f = None
    try:
        lng_f = float(lng) if lng is not None and str(lng).strip() != "" else None
    except Exception:
        lng_f = None
    webhook = str(
        data.get("securityWebhookUrl") or data.get("security_webhook_url") or cur["securityWebhookUrl"] or ""
    ).strip()[:500]
    escalate_after = _parse_escalate_minutes(
        data.get("escalateAfterMinutes", data.get("escalate_after_minutes", cur.get("escalateAfterMinutes"))),
        DEFAULT_ESCALATE_AFTER_MINUTES,
    )
    second_contact = str(
        data.get("escalateSecondContact")
        or data.get("escalate_second_contact")
        or cur.get("escalateSecondContact")
        or ""
    ).strip()[:200]
    if "requireDualAck" in data or "require_dual_ack" in data:
        require_dual = _parse_bool(data.get("requireDualAck", data.get("require_dual_ack")), True)
    else:
        require_dual = _parse_bool(cur.get("requireDualAck"), True)
    if "notifyRules" in data or "notify_rules" in data:
        notify_rules = _parse_notify_rules(data.get("notifyRules", data.get("notify_rules")))
    else:
        notify_rules = _parse_notify_rules(cur.get("notifyRules"))
    notify_json = _notify_rules_json(notify_rules)
    ts = now_iso()
    try:
        db.execute(
            """
            INSERT INTO camera_watch_settings (
                company_id, enabled, timezone, work_start, work_end, work_days,
                country, city, latitude, longitude, security_webhook_url,
                escalate_after_minutes, escalate_second_contact, require_dual_ack,
                notify_rules_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id) DO UPDATE SET
                enabled = excluded.enabled,
                timezone = excluded.timezone,
                work_start = excluded.work_start,
                work_end = excluded.work_end,
                work_days = excluded.work_days,
                country = excluded.country,
                city = excluded.city,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                security_webhook_url = excluded.security_webhook_url,
                escalate_after_minutes = excluded.escalate_after_minutes,
                escalate_second_contact = excluded.escalate_second_contact,
                require_dual_ack = excluded.require_dual_ack,
                notify_rules_json = excluded.notify_rules_json,
                updated_at = excluded.updated_at
            """,
            (
                cid,
                1 if enabled else 0,
                tz,
                work_start or DEFAULT_WORK_START,
                work_end or DEFAULT_WORK_END,
                work_days or DEFAULT_WORK_DAYS,
                country,
                city,
                lat_f,
                lng_f,
                webhook,
                escalate_after,
                second_contact,
                1 if require_dual else 0,
                notify_json,
                ts,
            ),
        )
        db.commit()
    except Exception:
        # Graceful: new columns missing — keep old INSERT path
        db.execute(
            """
            INSERT INTO camera_watch_settings (
                company_id, enabled, timezone, work_start, work_end, work_days,
                country, city, latitude, longitude, security_webhook_url, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id) DO UPDATE SET
                enabled = excluded.enabled,
                timezone = excluded.timezone,
                work_start = excluded.work_start,
                work_end = excluded.work_end,
                work_days = excluded.work_days,
                country = excluded.country,
                city = excluded.city,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                security_webhook_url = excluded.security_webhook_url,
                updated_at = excluded.updated_at
            """,
            (
                cid,
                1 if enabled else 0,
                tz,
                work_start or DEFAULT_WORK_START,
                work_end or DEFAULT_WORK_END,
                work_days or DEFAULT_WORK_DAYS,
                country,
                city,
                lat_f,
                lng_f,
                webhook,
                ts,
            ),
        )
        db.commit()
    return get_watch_settings(db, cid)


def _outside_work_window(current: time, start: time, end: time) -> bool:
    if start <= end:
        return not (start <= current < end)
    # overnight window (e.g. 22:00–06:00 means work overnight → after-hours is the daytime gap)
    return end <= current < start


def _resolve_tz(tz_name: str):
    name = str(tz_name or DEFAULT_TZ).strip() or DEFAULT_TZ
    if name.upper() in {"UTC", "GMT", "Z", "ETC/UTC"}:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:
        try:
            return ZoneInfo(DEFAULT_TZ)
        except Exception:
            return timezone.utc


def _find_watch_override(db, company_id: str, site_key: str, date_str: str):
    cid = str(company_id or "").strip()
    key = normalize_site_key(site_key)
    if not cid or not date_str:
        return None
    try:
        if key:
            row = db.execute(
                """
                SELECT * FROM camera_watch_overrides
                WHERE company_id = ? AND site_key = ? AND override_date = ?
                """,
                (cid, key, date_str),
            ).fetchone()
            if row:
                return row
        return db.execute(
            """
            SELECT * FROM camera_watch_overrides
            WHERE company_id = ? AND site_key = '' AND override_date = ?
            """,
            (cid, date_str),
        ).fetchone()
    except Exception:
        return None


def is_after_hours(
    db,
    company_id: str,
    *,
    at: datetime | None = None,
    settings: dict[str, Any] | None = None,
) -> bool:
    """True when watch is enabled and local time is outside configured work windows."""
    cfg = settings or get_watch_settings(db, company_id)
    if not cfg.get("enabled", True):
        return False
    tz = _resolve_tz(str(cfg.get("timezone") or DEFAULT_TZ))
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(tz)
    current = local.timetz().replace(tzinfo=None)
    date_str = local.date().isoformat()
    site_key = str(cfg.get("siteKey") or "")

    ovr = _find_watch_override(db, company_id, site_key, date_str)
    if ovr:
        kind = str(_row_get(ovr, "kind", "") or "").strip().lower()
        force_ah = _parse_bool(_row_get(ovr, "force_after_hours", 0), False)
        if kind in {"holiday", "force_watch", "force_after_hours"} or force_ah:
            return True
        if kind == "force_open":
            return False
        if kind == "special_hours":
            start = _parse_hhmm(
                str(_row_get(ovr, "work_start", "") or cfg.get("workStart") or DEFAULT_WORK_START),
                DEFAULT_WORK_START,
            )
            end = _parse_hhmm(
                str(_row_get(ovr, "work_end", "") or cfg.get("workEnd") or DEFAULT_WORK_END),
                DEFAULT_WORK_END,
            )
            return _outside_work_window(current, start, end)

    days = _parse_days(str(cfg.get("workDays") or DEFAULT_WORK_DAYS))
    if local.isoweekday() not in days:
        return True
    start = _parse_hhmm(str(cfg.get("workStart") or DEFAULT_WORK_START), DEFAULT_WORK_START)
    end = _parse_hhmm(str(cfg.get("workEnd") or DEFAULT_WORK_END), DEFAULT_WORK_END)
    return _outside_work_window(current, start, end)


def watch_status(db, company_id: str) -> dict[str, Any]:
    cfg = get_watch_settings(db, company_id)
    after = is_after_hours(db, company_id, settings=cfg)
    return {
        **cfg,
        "afterHours": after,
        "watchModeActive": bool(cfg.get("enabled")) and after,
        "label": "watch_active" if (cfg.get("enabled") and after) else ("watch_standby" if cfg.get("enabled") else "watch_off"),
    }


def severity_rank(sev: str) -> int:
    s = str(sev or "").lower()
    if s == "critical":
        return 3
    if s == "high":
        return 2
    if s == "medium":
        return 1
    return 0


def apply_after_hours_escalation(analysis: dict[str, Any], *, after_hours: bool) -> dict[str, Any]:
    """Boost severities and inject after-hours intrusion alerts when needed."""
    analysis = dict(analysis or {})
    alerts = [dict(a) for a in (analysis.get("alerts") or [])]
    event_type = str(analysis.get("event_type") or "motion").lower()
    analysis["afterHours"] = bool(after_hours)

    critical_types = {"restricted_zone", "forced_entry", "unknown_person", "possible_intrusion", "restricted_area_activity"}
    if after_hours:
        if event_type in {"motion", "person", "person_detected", "activity"} and not any(
            a.get("type") in critical_types for a in alerts
        ):
            alerts.append(
                {
                    "type": "after_hours_activity",
                    "severity": "high",
                    "message": "Activity detected outside business hours (suspicious incident — not confirmed theft)",
                }
            )
        for a in alerts:
            t = str(a.get("type") or "")
            if t in critical_types or t in {"after_hours_activity", "identity_mismatch", "tailgating"}:
                if severity_rank(a.get("severity")) < severity_rank("critical") and t in critical_types:
                    a["severity"] = "critical"
                elif t == "after_hours_activity":
                    a["severity"] = "high"
                elif t == "identity_mismatch" and after_hours:
                    a["severity"] = "critical"
                    a["message"] = "Identity mismatch outside business hours (unauthorized area risk)"

    max_sev = "info"
    for a in alerts:
        if severity_rank(a.get("severity")) > severity_rank(max_sev):
            max_sev = str(a.get("severity") or "info")
    analysis["alerts"] = alerts
    analysis["maxSeverity"] = max_sev
    analysis["snapshotRequired"] = max_sev == "critical" or any(
        str(a.get("type") or "") in critical_types | {"after_hours_activity"} for a in alerts
    )
    analysis["critical"] = max_sev == "critical" or any(
        str(a.get("type") or "") in critical_types for a in alerts
    )
    return analysis


def should_dedup_alert(db, company_id: str, camera_id: str, alert_key: str, *, minutes: int = 10) -> bool:
    """Return True if this alert was recently sent (skip)."""
    cid = str(company_id)
    cam = str(camera_id)
    key = str(alert_key)[:120]
    try:
        row = db.execute(
            """
            SELECT last_at FROM camera_vision_dedup
            WHERE company_id = ? AND camera_id = ? AND alert_key = ?
            """,
            (cid, cam, key),
        ).fetchone()
    except Exception:
        return False
    if not row:
        return False
    last = str(row["last_at"] or "")
    try:
        raw = last.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
        return age < max(60, minutes * 60)
    except Exception:
        return False


def mark_dedup_alert(db, company_id: str, camera_id: str, alert_key: str) -> None:
    ts = now_iso()
    try:
        db.execute(
            """
            INSERT INTO camera_vision_dedup (company_id, camera_id, alert_key, last_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(company_id, camera_id, alert_key) DO UPDATE SET last_at = excluded.last_at
            """,
            (str(company_id), str(camera_id), str(alert_key)[:120], ts),
        )
        db.commit()
    except Exception:
        pass


def settings_to_json(cfg: dict[str, Any]) -> str:
    return json.dumps(cfg, ensure_ascii=False)


def normalize_site_key(site: str | None) -> str:
    raw = str(site or "").strip().lower()
    if not raw:
        return ""
    out = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-_")[:80]


def _row_to_settings(cid: str, row, *, site_key: str = "", site_name: str = "") -> dict[str, Any]:
    return {
        "companyId": cid,
        "siteKey": site_key or str(_row_get(row, "site_key", "") or "") or "",
        "siteName": site_name or str(_row_get(row, "site_name", "") or "") or "",
        "enabled": bool(int(row["enabled"] or 0)),
        "timezone": str(row["timezone"] or DEFAULT_TZ),
        "workStart": str(row["work_start"] or DEFAULT_WORK_START),
        "workEnd": str(row["work_end"] or DEFAULT_WORK_END),
        "workDays": str(row["work_days"] or DEFAULT_WORK_DAYS),
        "country": str(row["country"] or ""),
        "city": str(row["city"] or ""),
        "latitude": float(row["latitude"]) if row["latitude"] is not None else None,
        "longitude": float(row["longitude"]) if row["longitude"] is not None else None,
        "securityWebhookUrl": str(row["security_webhook_url"] or ""),
        "escalateAfterMinutes": _parse_escalate_minutes(
            _row_get(row, "escalate_after_minutes", DEFAULT_ESCALATE_AFTER_MINUTES)
        ),
        "escalateSecondContact": str(_row_get(row, "escalate_second_contact", "") or ""),
        "requireDualAck": _parse_bool(_row_get(row, "require_dual_ack", 1), True),
        "notifyRules": _parse_notify_rules(_row_get(row, "notify_rules_json", "{}")),
        "updatedAt": str(row["updated_at"] or "") or None,
    }


def list_watch_sites(db, company_id: str) -> list[dict[str, Any]]:
    cid = str(company_id or "").strip()
    if not cid:
        return []
    try:
        rows = db.execute(
            """
            SELECT * FROM camera_watch_sites
            WHERE company_id = ?
            ORDER BY site_name COLLATE NOCASE, site_key
            """,
            (cid,),
        ).fetchall()
    except Exception:
        return []
    return [_row_to_settings(cid, r) for r in rows]


def get_site_watch_settings(db, company_id: str, site_key: str) -> dict[str, Any] | None:
    cid = str(company_id or "").strip()
    key = normalize_site_key(site_key)
    if not cid or not key:
        return None
    try:
        row = db.execute(
            "SELECT * FROM camera_watch_sites WHERE company_id = ? AND site_key = ?",
            (cid, key),
        ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return _row_to_settings(cid, row)


def upsert_site_watch_settings(
    db, company_id: str, site_key: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    key = normalize_site_key(site_key or (payload or {}).get("siteKey") or (payload or {}).get("site_key"))
    if not cid or not key:
        raise ValueError("site_key_required")
    data = payload or {}
    cur = get_site_watch_settings(db, cid, key) or {
        **default_watch_settings(cid),
        "siteKey": key,
        "siteName": str(data.get("siteName") or data.get("site_name") or site_key or key),
    }
    enabled = data.get("enabled")
    if enabled is None:
        enabled = cur.get("enabled", True)
    else:
        enabled = _parse_bool(enabled, True)
    site_name = str(data.get("siteName") or data.get("site_name") or cur.get("siteName") or key).strip()[:120]
    tz = str(data.get("timezone") or cur.get("timezone") or DEFAULT_TZ).strip() or DEFAULT_TZ
    work_start = str(data.get("workStart") or data.get("work_start") or cur.get("workStart") or DEFAULT_WORK_START)
    work_end = str(data.get("workEnd") or data.get("work_end") or cur.get("workEnd") or DEFAULT_WORK_END)
    work_days = str(data.get("workDays") or data.get("work_days") or cur.get("workDays") or DEFAULT_WORK_DAYS)
    country = str(data.get("country") or cur.get("country") or "").strip()[:80]
    city = str(data.get("city") or cur.get("city") or "").strip()[:120]
    try:
        lat_f = float(data["latitude"]) if data.get("latitude") not in (None, "") else cur.get("latitude")
    except Exception:
        lat_f = cur.get("latitude")
    try:
        lng_f = float(data["longitude"]) if data.get("longitude") not in (None, "") else cur.get("longitude")
    except Exception:
        lng_f = cur.get("longitude")
    webhook = str(
        data.get("securityWebhookUrl") or data.get("security_webhook_url") or cur.get("securityWebhookUrl") or ""
    ).strip()[:500]
    escalate_after = _parse_escalate_minutes(
        data.get("escalateAfterMinutes", data.get("escalate_after_minutes", cur.get("escalateAfterMinutes"))),
        DEFAULT_ESCALATE_AFTER_MINUTES,
    )
    second_contact = str(
        data.get("escalateSecondContact")
        or data.get("escalate_second_contact")
        or cur.get("escalateSecondContact")
        or ""
    ).strip()[:200]
    if "requireDualAck" in data or "require_dual_ack" in data:
        require_dual = _parse_bool(data.get("requireDualAck", data.get("require_dual_ack")), True)
    else:
        require_dual = _parse_bool(cur.get("requireDualAck"), True)
    if "notifyRules" in data or "notify_rules" in data:
        notify_rules = _parse_notify_rules(data.get("notifyRules", data.get("notify_rules")))
    else:
        notify_rules = _parse_notify_rules(cur.get("notifyRules"))
    notify_json = _notify_rules_json(notify_rules)
    ts = now_iso()
    try:
        db.execute(
            """
            INSERT INTO camera_watch_sites (
                company_id, site_key, site_name, enabled, timezone, work_start, work_end, work_days,
                country, city, latitude, longitude, security_webhook_url,
                escalate_after_minutes, escalate_second_contact, require_dual_ack,
                notify_rules_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, site_key) DO UPDATE SET
                site_name = excluded.site_name,
                enabled = excluded.enabled,
                timezone = excluded.timezone,
                work_start = excluded.work_start,
                work_end = excluded.work_end,
                work_days = excluded.work_days,
                country = excluded.country,
                city = excluded.city,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                security_webhook_url = excluded.security_webhook_url,
                escalate_after_minutes = excluded.escalate_after_minutes,
                escalate_second_contact = excluded.escalate_second_contact,
                require_dual_ack = excluded.require_dual_ack,
                notify_rules_json = excluded.notify_rules_json,
                updated_at = excluded.updated_at
            """,
            (
                cid,
                key,
                site_name,
                1 if enabled else 0,
                tz,
                work_start,
                work_end,
                work_days,
                country,
                city,
                lat_f,
                lng_f,
                webhook,
                escalate_after,
                second_contact,
                1 if require_dual else 0,
                notify_json,
                ts,
            ),
        )
        db.commit()
    except Exception:
        db.execute(
            """
            INSERT INTO camera_watch_sites (
                company_id, site_key, site_name, enabled, timezone, work_start, work_end, work_days,
                country, city, latitude, longitude, security_webhook_url, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, site_key) DO UPDATE SET
                site_name = excluded.site_name,
                enabled = excluded.enabled,
                timezone = excluded.timezone,
                work_start = excluded.work_start,
                work_end = excluded.work_end,
                work_days = excluded.work_days,
                country = excluded.country,
                city = excluded.city,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                security_webhook_url = excluded.security_webhook_url,
                updated_at = excluded.updated_at
            """,
            (
                cid,
                key,
                site_name,
                1 if enabled else 0,
                tz,
                work_start,
                work_end,
                work_days,
                country,
                city,
                lat_f,
                lng_f,
                webhook,
                ts,
            ),
        )
        db.commit()
    return get_site_watch_settings(db, cid, key) or cur


def delete_site_watch_settings(db, company_id: str, site_key: str) -> bool:
    cid = str(company_id or "").strip()
    key = normalize_site_key(site_key)
    if not cid or not key:
        return False
    cur = db.execute(
        "DELETE FROM camera_watch_sites WHERE company_id = ? AND site_key = ?",
        (cid, key),
    )
    db.commit()
    return int(getattr(cur, "rowcount", 0) or 0) > 0


def _serialize_override(row) -> dict[str, Any]:
    return {
        "companyId": str(row["company_id"]),
        "siteKey": str(_row_get(row, "site_key", "") or ""),
        "overrideDate": str(row["override_date"]),
        "kind": str(row["kind"] or "holiday"),
        "workStart": str(_row_get(row, "work_start", "") or ""),
        "workEnd": str(_row_get(row, "work_end", "") or ""),
        "forceAfterHours": _parse_bool(_row_get(row, "force_after_hours", 0), False),
        "note": str(_row_get(row, "note", "") or ""),
        "createdAt": str(_row_get(row, "created_at", "") or "") or None,
    }


def list_watch_overrides(db, company_id: str) -> list[dict[str, Any]]:
    cid = str(company_id or "").strip()
    if not cid:
        return []
    try:
        rows = db.execute(
            """
            SELECT * FROM camera_watch_overrides
            WHERE company_id = ?
            ORDER BY override_date DESC, site_key
            """,
            (cid,),
        ).fetchall()
    except Exception:
        return []
    return [_serialize_override(r) for r in rows]


def upsert_watch_override(db, company_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    if not cid:
        raise ValueError("company_id_required")
    data = payload or {}
    override_date = str(data.get("overrideDate") or data.get("override_date") or "").strip()[:10]
    if not override_date:
        raise ValueError("override_date_required")
    site_key = normalize_site_key(data.get("siteKey") or data.get("site_key") or "")
    kind = str(data.get("kind") or "holiday").strip().lower()
    if kind not in OVERRIDE_KINDS:
        raise ValueError("invalid_override_kind")
    work_start = str(data.get("workStart") or data.get("work_start") or "").strip()[:8]
    work_end = str(data.get("workEnd") or data.get("work_end") or "").strip()[:8]
    note = str(data.get("note") or "").strip()[:500]
    force_after = 1 if kind in {"holiday", "force_watch", "force_after_hours"} else 0
    if "forceAfterHours" in data or "force_after_hours" in data:
        force_after = 1 if _parse_bool(data.get("forceAfterHours", data.get("force_after_hours")), False) else 0
    ts = now_iso()
    db.execute(
        """
        INSERT INTO camera_watch_overrides (
            company_id, site_key, override_date, kind, work_start, work_end,
            force_after_hours, note, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id, site_key, override_date) DO UPDATE SET
            kind = excluded.kind,
            work_start = excluded.work_start,
            work_end = excluded.work_end,
            force_after_hours = excluded.force_after_hours,
            note = excluded.note
        """,
        (cid, site_key, override_date, kind, work_start, work_end, force_after, note, ts),
    )
    db.commit()
    row = db.execute(
        """
        SELECT * FROM camera_watch_overrides
        WHERE company_id = ? AND site_key = ? AND override_date = ?
        """,
        (cid, site_key, override_date),
    ).fetchone()
    return _serialize_override(row) if row else {
        "companyId": cid,
        "siteKey": site_key,
        "overrideDate": override_date,
        "kind": kind,
        "workStart": work_start,
        "workEnd": work_end,
        "forceAfterHours": bool(force_after),
        "note": note,
        "createdAt": ts,
    }


def delete_watch_override(db, company_id: str, override_date: str, site_key: str = "") -> bool:
    cid = str(company_id or "").strip()
    date_str = str(override_date or "").strip()[:10]
    key = normalize_site_key(site_key)
    if not cid or not date_str:
        return False
    cur = db.execute(
        """
        DELETE FROM camera_watch_overrides
        WHERE company_id = ? AND site_key = ? AND override_date = ?
        """,
        (cid, key, date_str),
    )
    db.commit()
    return int(getattr(cur, "rowcount", 0) or 0) > 0


def resolve_watch_settings(db, company_id: str, *, site: str | None = None) -> dict[str, Any]:
    """Company defaults, overridden by site settings when site_key matches camera location."""
    company = get_watch_settings(db, company_id)
    key = normalize_site_key(site)
    if not key:
        return {**company, "siteKey": "", "resolvedFrom": "company"}
    site_cfg = get_site_watch_settings(db, company_id, key)
    if not site_cfg:
        return {**company, "siteKey": key, "resolvedFrom": "company"}
    merged = {**company, **site_cfg, "resolvedFrom": "site"}
    return merged


def is_after_hours_for_site(
    db,
    company_id: str,
    *,
    site: str | None = None,
    at: datetime | None = None,
) -> bool:
    cfg = resolve_watch_settings(db, company_id, site=site)
    return is_after_hours(db, company_id, at=at, settings=cfg)


def is_alert_suppressed(db, company_id: str, camera_id: str, alert_key: str) -> bool:
    """True when false-positive learning still suppresses this alert key."""
    try:
        row = db.execute(
            """
            SELECT suppress_until FROM camera_alert_thresholds
            WHERE company_id = ? AND camera_id = ? AND alert_key = ?
            """,
            (str(company_id), str(camera_id), str(alert_key)[:120]),
        ).fetchone()
    except Exception:
        return False
    if not row or not row["suppress_until"]:
        return False
    try:
        raw = str(row["suppress_until"]).replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < dt.astimezone(timezone.utc)
    except Exception:
        return False


def record_false_positive_learning(
    db,
    company_id: str,
    camera_id: str,
    alert_key: str,
    *,
    boost_minutes: int = 60,
) -> dict[str, Any]:
    """Increase FP count and extend suppress window (learns quieter thresholds)."""
    cid, cam, key = str(company_id), str(camera_id), str(alert_key)[:120]
    ts = now_iso()
    try:
        row = db.execute(
            """
            SELECT false_positive_count, suppress_minutes FROM camera_alert_thresholds
            WHERE company_id = ? AND camera_id = ? AND alert_key = ?
            """,
            (cid, cam, key),
        ).fetchone()
    except Exception:
        row = None
    count = int(row["false_positive_count"] or 0) + 1 if row else 1
    base_min = int(row["suppress_minutes"] or 30) if row else 30
    suppress_min = min(24 * 60, max(boost_minutes, base_min * min(count, 4)))
    until = datetime.now(timezone.utc).timestamp() + suppress_min * 60
    until_iso = datetime.fromtimestamp(until, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    try:
        db.execute(
            """
            INSERT INTO camera_alert_thresholds (
                company_id, camera_id, alert_key, false_positive_count,
                suppress_minutes, suppress_until, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, camera_id, alert_key) DO UPDATE SET
                false_positive_count = excluded.false_positive_count,
                suppress_minutes = excluded.suppress_minutes,
                suppress_until = excluded.suppress_until,
                updated_at = excluded.updated_at
            """,
            (cid, cam, key, count, suppress_min, until_iso, ts),
        )
        db.commit()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "falsePositiveCount": count,
        "suppressMinutes": suppress_min,
        "suppressUntil": until_iso,
    }
