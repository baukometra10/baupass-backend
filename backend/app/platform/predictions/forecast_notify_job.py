"""Morning tomorrow-forecast employer notifications."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger("baupass.predictions.forecast_notify")


def _forecast_notify_hour() -> int:
    return max(0, min(23, int(os.getenv("BAUPASS_FORECAST_NOTIFY_HOUR", "7"))))


def _default_tz_name() -> str:
    return (os.getenv("BAUPASS_FORECAST_NOTIFY_TZ") or "Europe/Berlin").strip() or "Europe/Berlin"


def _company_local_now(db, company_id: str) -> datetime | None:
    tz_name = _default_tz_name()
    try:
        row = db.execute(
            "SELECT report_timezone FROM companies WHERE id = ?",
            (str(company_id),),
        ).fetchone()
        if row and "report_timezone" in row.keys() and str(row["report_timezone"] or "").strip():
            tz_name = str(row["report_timezone"]).strip()
    except Exception:
        pass
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz)


def run_forecast_notify_cycle(db, *, force: bool = False) -> dict[str, Any]:
    """
    Notify company admins about tomorrow attendance risk.

    Intended to run periodically (e.g. report scheduler). Sends once per company
    per morning hour window when expectedAbsent > 0.
    """
    from backend.app.platform.notifications.company_mitteilung import (
        notify_company_tomorrow_forecast,
    )
    from backend.app.platform.predictions.engine import build_tomorrow_forecast

    target_hour = _forecast_notify_hour()
    rows = db.execute(
        """
        SELECT id
        FROM companies
        WHERE deleted_at IS NULL
          AND COALESCE(status, 'aktiv') NOT IN ('gesperrt', 'suspended', 'inactive')
        ORDER BY id
        """
    ).fetchall()

    processed = 0
    notified = 0
    skipped = 0
    errors: list[str] = []

    for row in rows:
        cid = str(row["id"] or "").strip()
        if not cid:
            continue
        processed += 1
        try:
            if not force:
                local_now = _company_local_now(db, cid)
                if local_now is None or local_now.hour != target_hour:
                    skipped += 1
                    continue
            forecast = build_tomorrow_forecast(db, cid)
            if int(forecast.get("expectedAbsent") or 0) <= 0:
                skipped += 1
                continue
            result = notify_company_tomorrow_forecast(db, company_id=cid, forecast=forecast)
            if result.get("deduped") or result.get("skipped"):
                skipped += 1
            else:
                notified += 1
        except Exception as exc:
            errors.append(f"{cid}:{exc}")
            logger.debug("forecast notify failed for %s", cid, exc_info=True)

    return {
        "ok": True,
        "processed": processed,
        "notified": notified,
        "skipped": skipped,
        "errors": errors[:20],
        "hour": target_hour,
    }
