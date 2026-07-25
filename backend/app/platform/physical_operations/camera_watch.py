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
        enabled = bool(enabled) if not isinstance(enabled, str) else enabled.lower() in {"1", "true", "yes", "on"}
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
    ts = now_iso()
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
    tz_name = str(cfg.get("timezone") or DEFAULT_TZ)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(DEFAULT_TZ)
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(tz)
    days = _parse_days(str(cfg.get("workDays") or DEFAULT_WORK_DAYS))
    if local.isoweekday() not in days:
        return True
    start = _parse_hhmm(str(cfg.get("workStart") or DEFAULT_WORK_START), DEFAULT_WORK_START)
    end = _parse_hhmm(str(cfg.get("workEnd") or DEFAULT_WORK_END), DEFAULT_WORK_END)
    current = local.timetz().replace(tzinfo=None)
    if start <= end:
        return not (start <= current < end)
    # overnight window (e.g. 22:00–06:00 means work overnight → after-hours is the daytime gap)
    return end <= current < start


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
