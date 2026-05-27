"""Shared helpers for Physical Operations OS."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def today_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def company_id_from_user(user: dict, request_args: Any = None) -> int:
    if user.get("role") == "superadmin" and request_args:
        raw = str(request_args.get("company_id", "")).strip()
        if raw.isdigit():
            return int(raw)
    return int(user.get("company_id") or 0)


def workers_on_site_sql(alias: str = "w") -> str:
    """Subquery-friendly: latest direction per worker today."""
    return f"""
        SELECT al.worker_id, al.direction, al.gate, al.timestamp
        FROM access_logs al
        JOIN workers {alias} ON {alias}.id = al.worker_id
        WHERE {alias}.company_id = ? AND {alias}.deleted_at IS NULL
          AND al.timestamp LIKE ?
          AND al.timestamp = (
              SELECT MAX(al2.timestamp) FROM access_logs al2
              WHERE al2.worker_id = al.worker_id AND al2.timestamp LIKE ?
          )
    """


def _cid_param(company_id: int) -> str | int:
    return str(company_id)


def count_on_site(db, company_id: int, today: str | None = None) -> int:
    today = today or today_prefix()
    cid = _cid_param(company_id)
    row = db.execute(
        f"""
        SELECT COUNT(*) AS c FROM ({workers_on_site_sql("w")}) latest
        WHERE latest.direction = 'check-in'
        """,
        (cid, f"{today}%", f"{today}%"),
    ).fetchone()
    return int((row["c"] if row else 0) or 0)


def list_on_site_workers(db, company_id: int, today: str | None = None) -> list[dict]:
    today = today or today_prefix()
    cid = _cid_param(company_id)
    rows = db.execute(
        f"""
        SELECT w.id, w.first_name, w.last_name, w.site, w.badge_id, w.status,
               latest.gate, latest.timestamp AS last_access
        FROM ({workers_on_site_sql("w")}) latest
        JOIN workers w ON w.id = latest.worker_id
        WHERE latest.direction = 'check-in'
        ORDER BY latest.timestamp DESC
        """,
        (cid, f"{today}%", f"{today}%"),
    ).fetchall()
    return [dict(r) for r in rows]
