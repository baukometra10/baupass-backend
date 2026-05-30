"""Timezone-aware scheduling for daily report emails (default 08:00 local)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def default_platform_timezone() -> str:
    return (os.getenv("BAUPASS_TIMEZONE", "Europe/Berlin") or "Europe/Berlin").strip()


def daily_report_hour() -> int:
    try:
        return max(0, min(23, int(os.getenv("BAUPASS_DAILY_REPORT_HOUR", "8"))))
    except ValueError:
        return 8


def report_scheduler_interval_seconds() -> int:
    try:
        minutes = max(5, int(os.getenv("BAUPASS_REPORT_SCHEDULER_MINUTES", "15")))
    except ValueError:
        minutes = 15
    return minutes * 60


def resolve_company_timezone(db, company_id: str) -> str:
    tz_name = ""
    try:
        row = db.execute(
            "SELECT report_timezone FROM companies WHERE id = ?",
            (str(company_id),),
        ).fetchone()
        if row:
            tz_name = str(row["report_timezone"] or "").strip()
    except Exception:
        tz_name = ""
    return tz_name or default_platform_timezone()


def local_now_for_timezone(tz_name: str) -> datetime:
    try:
        tz = ZoneInfo(tz_name or default_platform_timezone())
    except Exception:
        tz = ZoneInfo("Europe/Berlin")
    return datetime.now(timezone.utc).astimezone(tz)


def is_daily_report_send_window(tz_name: str, *, now_utc: datetime | None = None) -> bool:
    """
    True during the configured local hour (default 08:00–08:14).
    Checked every BAUPASS_REPORT_SCHEDULER_MINUTES by the report scheduler loop.
    """
    try:
        tz = ZoneInfo(tz_name or default_platform_timezone())
    except Exception:
        tz = ZoneInfo("Europe/Berlin")
    ref = (now_utc or datetime.now(timezone.utc)).astimezone(tz)
    hour = daily_report_hour()
    try:
        tolerance = max(0, min(59, int(os.getenv("BAUPASS_DAILY_REPORT_MINUTE_END", "14"))))
    except ValueError:
        tolerance = 14
    return ref.hour == hour and ref.minute <= tolerance


def local_day_key(tz_name: str, *, now_utc: datetime | None = None) -> str:
    return local_now_for_timezone(tz_name).date().isoformat()
