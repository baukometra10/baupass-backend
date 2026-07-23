"""Consecutive late check-in streaks for employer alerts."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

LATE_STREAK_THRESHOLD = 3
LATE_STREAK_LOOKBACK_DAYS = 30


def _day_key(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return raw[:10]


def list_late_checkin_evidence(
    db,
    worker_id: str,
    *,
    limit: int = 8,
    lookback_days: int = LATE_STREAK_LOOKBACK_DAYS,
) -> list[dict[str, Any]]:
    """Recent late check-ins with gate/time — used as employer-facing 'why' evidence."""
    wid = str(worker_id or "").strip()
    if not wid:
        return []
    since = (date.today() - timedelta(days=max(7, int(lookback_days or 30)))).isoformat()
    rows = db.execute(
        """
        SELECT timestamp, gate, note, checked_in_late
        FROM access_logs
        WHERE worker_id = ?
          AND direction = 'check-in'
          AND COALESCE(checked_in_late, 0) = 1
          AND timestamp >= ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (wid, since, max(1, min(30, int(limit or 8)))),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        ts = str(row["timestamp"] or "")
        out.append(
            {
                "at": ts,
                "day": ts[:10],
                "time": (ts[11:16] if len(ts) >= 16 else ""),
                "gate": str(row["gate"] or "").strip() or "—",
                "note": str(row["note"] or "").strip()[:160],
                "reason": "late_checkin",
            }
        )
    return out


def summarize_late_evidence(events: list[dict[str, Any]], *, lang: str = "de") -> str:
    """Short human reason string from evidence rows."""
    if not events:
        if lang == "ar":
            return "لا تفاصيل إضافية عن أوقات التأخر."
        if lang == "en":
            return "No detailed late timestamps on file."
        return "Keine weiteren Verspätungszeiten hinterlegt."
    bits = []
    for ev in events[:5]:
        day = ev.get("day") or ""
        time = ev.get("time") or ""
        gate = ev.get("gate") or "—"
        if lang == "ar":
            bits.append(f"{day} الساعة {time or '—'} (البوابة {gate})")
        elif lang == "en":
            bits.append(f"{day} at {time or '—'} (gate {gate})")
        else:
            bits.append(f"{day} um {time or '—'} Uhr (Tor {gate})")
    if lang == "ar":
        return "أوقات التأخر المسجّلة: " + "؛ ".join(bits)
    if lang == "en":
        return "Recorded late check-ins: " + "; ".join(bits)
    return "Erfasste Verspätungen: " + "; ".join(bits)


def count_consecutive_late_checkins(
    db,
    worker_id: str,
    *,
    limit_days: int = LATE_STREAK_LOOKBACK_DAYS,
    as_of: date | None = None,
) -> int:
    """
    Count consecutive calendar days (newest first) where the worker had a late check-in.

    A day is late when MAX(checked_in_late) for that day's check-ins is 1.
    Streak breaks on the first day with a non-late check-in.
    """
    day = as_of or date.today()
    lookback = max(7, int(limit_days or LATE_STREAK_LOOKBACK_DAYS))
    since = (day - timedelta(days=lookback)).isoformat()
    rows = db.execute(
        """
        SELECT SUBSTR(timestamp, 1, 10) AS work_day,
               MAX(COALESCE(checked_in_late, 0)) AS was_late
        FROM access_logs
        WHERE worker_id = ?
          AND direction = 'check-in'
          AND timestamp >= ?
        GROUP BY SUBSTR(timestamp, 1, 10)
        ORDER BY work_day DESC
        LIMIT ?
        """,
        (str(worker_id), since, lookback),
    ).fetchall()
    streak = 0
    for row in rows:
        was_late = int(row["was_late"] or 0) == 1
        if was_late:
            streak += 1
            continue
        break
    return streak


def evaluate_late_streak_after_checkin(
    db,
    worker: Any,
    *,
    late: bool,
    threshold: int = LATE_STREAK_THRESHOLD,
) -> dict[str, Any] | None:
    """Return streak payload when this late check-in reaches the employer-alert threshold."""
    if not late:
        return None
    try:
        worker_id = str(worker["id"])
        company_id = str(worker["company_id"])
        first = str(worker["first_name"] or "").strip()
        last = str(worker["last_name"] or "").strip()
        worker_name = f"{first} {last}".strip() or worker_id
    except Exception:
        return None
    streak = count_consecutive_late_checkins(db, worker_id)
    if streak < int(threshold or LATE_STREAK_THRESHOLD):
        return None
    evidence = list_late_checkin_evidence(db, worker_id, limit=max(streak, 5))
    return {
        "companyId": company_id,
        "workerId": worker_id,
        "workerName": worker_name,
        "streak": streak,
        "threshold": int(threshold or LATE_STREAK_THRESHOLD),
        "lateEvents": evidence,
        "reasonSummary": summarize_late_evidence(evidence),
    }


def list_repeated_late_workers(
    db,
    company_id: str,
    *,
    min_streak: int = LATE_STREAK_THRESHOLD,
    limit: int = 10,
    lookback_days: int = 21,
) -> list[dict[str, Any]]:
    """Workers in company with consecutive late streak >= min_streak (capped list)."""
    cid = str(company_id or "").strip()
    if not cid:
        return []
    since = (date.today() - timedelta(days=max(7, lookback_days))).isoformat()
    candidates = db.execute(
        """
        SELECT w.id, w.first_name, w.last_name
        FROM workers w
        WHERE w.company_id = ?
          AND w.deleted_at IS NULL
          AND COALESCE(w.worker_type, 'worker') = 'worker'
          AND EXISTS (
            SELECT 1 FROM access_logs al
            WHERE al.worker_id = w.id
              AND al.direction = 'check-in'
              AND COALESCE(al.checked_in_late, 0) = 1
              AND al.timestamp >= ?
          )
        ORDER BY w.last_name, w.first_name
        LIMIT 80
        """,
        (cid, since),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in candidates:
        wid = str(row["id"])
        streak = count_consecutive_late_checkins(db, wid, limit_days=lookback_days)
        if streak < int(min_streak or LATE_STREAK_THRESHOLD):
            continue
        first = str(row["first_name"] or "").strip()
        last = str(row["last_name"] or "").strip()
        out.append(
            {
                "workerId": wid,
                "name": f"{first} {last}".strip() or wid,
                "streak": streak,
            }
        )
    out.sort(key=lambda item: (-int(item["streak"]), str(item["name"])))
    return out[: max(1, int(limit or 10))]
