"""Shared helpers for Physical Operations OS."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def today_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


ON_SITE_DIRECTIONS = ("check-in", "app-login")
OFF_SITE_DIRECTIONS = ("check-out", "app-logout")


def is_on_site_direction(direction: str | None) -> bool:
    return str(direction or "").strip().lower() in ON_SITE_DIRECTIONS


def on_site_direction_sql(column: str = "latest.direction") -> str:
    return f"{column} IN ('check-in', 'app-login')"


def _present_on_site_sql_body(*, worker_ref: str = "w.id") -> str:
    """Shared SQL: worker currently present on site (open check-in or active GPS session)."""
    return f"""
        (
            EXISTS (
                SELECT 1 FROM access_logs al_in
                WHERE al_in.worker_id = {worker_ref}
                  AND al_in.timestamp LIKE ?
                  AND al_in.direction = 'check-in'
                  AND NOT EXISTS (
                      SELECT 1 FROM access_logs al_out
                      WHERE al_out.worker_id = al_in.worker_id
                        AND al_out.timestamp > al_in.timestamp
                        AND al_out.timestamp LIKE ?
                        AND al_out.direction = 'check-out'
                  )
            )
            OR (
                EXISTS (
                    SELECT 1 FROM access_logs al
                    WHERE al.worker_id = {worker_ref}
                      AND al.timestamp LIKE ?
                      AND al.direction = 'app-login'
                      AND al.timestamp = (
                          SELECT MAX(al2.timestamp) FROM access_logs al2
                          WHERE al2.worker_id = al.worker_id AND al2.timestamp LIKE ?
                      )
                )
                AND EXISTS (
                    SELECT 1 FROM worker_app_sessions was
                    WHERE was.worker_id = {worker_ref} AND was.expires_at >= ?
                )
            )
        )
    """


def _present_on_site_params(today: str, now: str | None = None) -> tuple[str, str, str, str, str]:
    prefix = f"{today}%"
    return prefix, prefix, prefix, prefix, now or now_iso()


def is_worker_present_on_site_today(db, worker_id: str, today: str | None = None) -> bool:
    today = today or today_prefix()
    wid = str(worker_id or "").strip()
    if not wid:
        return False
    now = now_iso()
    prefix, p2, p3, p4, p5 = _present_on_site_params(today, now)
    row = db.execute(
        f"""
        SELECT 1
        FROM workers w
        WHERE w.id = ? AND w.deleted_at IS NULL
          AND {_present_on_site_sql_body(worker_ref="w.id")}
        LIMIT 1
        """,
        (wid, prefix, p2, p3, p4, p5),
    ).fetchone()
    return bool(row)


def as_company_id(value: Any) -> str:
    """Company ids are strings like cmp-abc123 — never int()."""
    return str(value or "").strip()


def company_id_from_user(user: dict, request_args: Any = None) -> str:
    if user.get("role") == "superadmin" and request_args:
        raw = str(request_args.get("company_id", "")).strip()
        if raw:
            return raw
    return str(user.get("company_id") or "").strip()


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


def _cid_param(company_id: str) -> str:
    return str(company_id or "").strip()


def count_on_site(db, company_id: str, today: str | None = None) -> int:
    return count_on_site_filtered(db, "AND w.company_id = ?", [_cid_param(company_id)], today)


def count_on_site_filtered(
    db,
    company_sql: str,
    company_params: list[Any],
    today: str | None = None,
) -> int:
    today = today or today_prefix()
    prefix, p2, p3, p4, p5 = _present_on_site_params(today)
    row = db.execute(
        f"""
        SELECT COUNT(DISTINCT w.id) AS c
        FROM workers w
        WHERE w.deleted_at IS NULL
          {company_sql}
          AND {_present_on_site_sql_body(worker_ref="w.id")}
        """,
        tuple(company_params + [prefix, p2, p3, p4, p5]),
    ).fetchone()
    return int((row["c"] if row else 0) or 0)


def geo_offset(lat: float, lng: float, seed: str) -> tuple[float, float]:
    """Spread markers that share the same coordinates."""
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    return (
        lat + 0.00025 * (h % 5) * (1 if h % 2 else -1),
        lng + 0.00035 * ((h >> 4) % 5) * (1 if (h >> 8) % 2 else -1),
    )


def geofence_site_index(db, company_id: str) -> dict[str, dict[str, Any]]:
    cid = _cid_param(company_id)
    out: dict[str, dict[str, Any]] = {}
    try:
        rows = db.execute(
            """
            SELECT site_name, latitude, longitude, radius_meters
            FROM geofences WHERE company_id = ? AND active = 1
            """,
            (cid,),
        ).fetchall()
        for r in rows:
            name = str(r["site_name"] or "").strip()
            if name and r["latitude"] is not None and r["longitude"] is not None:
                out[name] = dict(r)
    except Exception:
        pass
    return out


def resolve_map_coordinates(
    db,
    company_id: str,
    *,
    lat: Any = None,
    lng: Any = None,
    site: str = "",
    seed: str = "",
) -> dict[str, float] | None:
    """Real lat/lng from worker site, geofence name, or company geofences — no synthetic grid."""
    try:
        if lat is not None and lng is not None:
            la, ln = float(lat), float(lng)
            if seed:
                la, ln = geo_offset(la, ln, seed)
            return {"lat": la, "lng": ln}
    except (TypeError, ValueError):
        pass
    idx = geofence_site_index(db, company_id)
    site_key = (site or "").strip()
    if site_key and site_key in idx:
        la, ln = float(idx[site_key]["latitude"]), float(idx[site_key]["longitude"])
        if seed:
            la, ln = geo_offset(la, ln, seed)
        return {"lat": la, "lng": ln}
    if idx:
        first = next(iter(idx.values()))
        la, ln = float(first["latitude"]), float(first["longitude"])
        if seed:
            la, ln = geo_offset(la, ln, seed)
        return {"lat": la, "lng": ln}
    return None


def list_on_site_workers(db, company_id: str, today: str | None = None) -> list[dict]:
    today = today or today_prefix()
    cid = _cid_param(company_id)
    prefix, p2, p3, p4, p5 = _present_on_site_params(today)
    rows = db.execute(
        f"""
        SELECT w.id, w.first_name, w.last_name, w.site, w.badge_id, w.status,
               w.site_latitude, w.site_longitude,
               COALESCE(latest.gate, '') AS gate,
               COALESCE(latest.timestamp, '') AS last_access
        FROM workers w
        LEFT JOIN (
            SELECT al.worker_id, al.direction, al.gate, al.timestamp
            FROM access_logs al
            WHERE al.timestamp LIKE ?
              AND al.timestamp = (
                  SELECT MAX(al2.timestamp) FROM access_logs al2
                  WHERE al2.worker_id = al.worker_id AND al2.timestamp LIKE ?
              )
        ) latest ON latest.worker_id = w.id
        WHERE w.company_id = ? AND w.deleted_at IS NULL
          AND {_present_on_site_sql_body(worker_ref="w.id")}
        ORDER BY last_access DESC
        """,
        (prefix, prefix, cid, prefix, p2, p3, p4, p5),
    ).fetchall()
    return [dict(r) for r in rows]
