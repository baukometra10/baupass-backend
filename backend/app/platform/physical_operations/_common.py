"""Shared helpers for Physical Operations OS."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def today_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


ON_SITE_DIRECTIONS = ("check-in", "app-login")
OFF_SITE_DIRECTIONS = ("check-out", "app-logout")
WORK_CHECKIN_DIRECTIONS = ("check-in",)
WORK_CHECKOUT_DIRECTIONS = ("check-out",)


def _access_wall_tz():
    try:
        return ZoneInfo("Europe/Berlin")
    except Exception:
        # Windows/dev without tzdata: CEST-ish fallback (Railway/Linux has zoneinfo data).
        return timezone(timedelta(hours=2))


ACCESS_WALL_TZ = _access_wall_tz()


def is_work_checkin(direction: str | None) -> bool:
    return str(direction or "").strip().lower() in WORK_CHECKIN_DIRECTIONS


def is_work_checkout(direction: str | None) -> bool:
    return str(direction or "").strip().lower() in WORK_CHECKOUT_DIRECTIONS


def is_on_site_direction(direction: str | None) -> bool:
    return str(direction or "").strip().lower() in ON_SITE_DIRECTIONS


def is_off_site_direction(direction: str | None) -> bool:
    return str(direction or "").strip().lower() in OFF_SITE_DIRECTIONS


def _parse_access_timestamp(value: str | None) -> datetime | None:
    """
    Parse access-log timestamps into comparable Europe/Berlin datetimes.

    - Explicit Z/offset → convert to Berlin
    - Naive ISO (mobile / auto Schichtende) → treat as Berlin wall clock
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith(("Z", "z")):
            dt = datetime.fromisoformat(raw[:-1] + "+00:00")
        elif len(raw) > 19 and (raw[19] in "+-" or "+" in raw[10:] or raw.count("-") >= 3):
            dt = datetime.fromisoformat(raw)
        else:
            dt = datetime.fromisoformat(raw[:19])
            return dt.replace(tzinfo=ACCESS_WALL_TZ)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=ACCESS_WALL_TZ)
        return dt.astimezone(ACCESS_WALL_TZ)
    except ValueError:
        return None


def _access_event_sort_key(item: dict[str, Any]) -> tuple[datetime, str]:
    parsed = _parse_access_timestamp(item.get("timestamp"))
    stamp = str(item.get("timestamp") or "")
    if parsed is None:
        return (datetime.min.replace(tzinfo=ACCESS_WALL_TZ), stamp)
    return (parsed, stamp)


def minutes_between_access_timestamps(start: str | None, end: str | None) -> int | None:
    """Positive elapsed minutes between access events; rounds up (min 1 min)."""
    t_in = _parse_access_timestamp(start)
    t_out = _parse_access_timestamp(end)
    if not t_in or not t_out or t_out <= t_in:
        return None
    seconds = int((t_out - t_in).total_seconds())
    if seconds <= 0:
        return None
    return min(max(1, (seconds + 59) // 60), 1439)


def pair_presence_sessions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chronologically pair check-in/app-login with check-out/app-logout."""
    ordered = sorted(events, key=_access_event_sort_key)
    sessions: list[dict[str, Any]] = []
    pending_in: dict[str, Any] | None = None

    for ev in ordered:
        direction = str(ev.get("direction") or "").strip().lower()
        if is_on_site_direction(direction):
            if pending_in is None:
                pending_in = ev
            continue
        if not is_off_site_direction(direction):
            continue

        duration = None
        if pending_in:
            duration = minutes_between_access_timestamps(
                pending_in.get("timestamp"), ev.get("timestamp")
            )
            sessions.append(
                {
                    "checkIn": pending_in.get("timestamp"),
                    "checkOut": ev.get("timestamp"),
                    "gateIn": pending_in.get("gate") or "",
                    "gateOut": ev.get("gate") or "",
                    "durationMinutes": duration,
                }
            )
            pending_in = None
        else:
            sessions.append(
                {
                    "checkIn": None,
                    "checkOut": ev.get("timestamp"),
                    "gateIn": "",
                    "gateOut": ev.get("gate") or "",
                    "durationMinutes": None,
                }
            )

    if pending_in:
        sessions.append(
            {
                "checkIn": pending_in.get("timestamp"),
                "checkOut": None,
                "gateIn": pending_in.get("gate") or "",
                "gateOut": "",
                "durationMinutes": None,
            }
        )

    return sessions


def pair_work_attendance_sessions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair only formal check-in / check-out for billable work hours."""
    ordered = sorted(events, key=_access_event_sort_key)
    sessions: list[dict[str, Any]] = []
    pending_in: dict[str, Any] | None = None

    for ev in ordered:
        direction = str(ev.get("direction") or "").strip().lower()
        if is_work_checkin(direction):
            if pending_in is None:
                pending_in = ev
            continue
        if not is_work_checkout(direction):
            continue

        duration = None
        if pending_in:
            duration = minutes_between_access_timestamps(
                pending_in.get("timestamp"), ev.get("timestamp")
            )
            sessions.append(
                {
                    "checkIn": pending_in.get("timestamp"),
                    "checkOut": ev.get("timestamp"),
                    "gateIn": pending_in.get("gate") or "",
                    "gateOut": ev.get("gate") or "",
                    "durationMinutes": duration,
                }
            )
            pending_in = None

    if pending_in:
        sessions.append(
            {
                "checkIn": pending_in.get("timestamp"),
                "checkOut": None,
                "gateIn": pending_in.get("gate") or "",
                "gateOut": "",
                "durationMinutes": None,
            }
        )

    return sessions


def total_work_attendance_minutes(
    events: list[dict[str, Any]],
    *,
    open_checkin_at: str | None = None,
) -> int:
    """Billable minutes from closed check-in/out pairs plus one open check-in when provided."""
    total = 0
    for session in pair_work_attendance_sessions(events):
        minutes = session.get("durationMinutes")
        if isinstance(minutes, int) and minutes > 0:
            total += minutes
    if open_checkin_at:
        extra = minutes_between_access_timestamps(open_checkin_at, now_iso())
        if isinstance(extra, int) and extra > 0:
            total += extra
    return total


def today_work_minutes(
    events: list[dict[str, Any]],
    *,
    open_checkin_at: str | None = None,
    day_prefix: str | None = None,
) -> int:
    """Work minutes for a calendar day, including an overnight open check-in from yesterday."""
    day = day_prefix or today_prefix()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    day_events = [ev for ev in events if str(ev.get("timestamp") or "")[:10] == day]
    open_for_day = None
    if open_checkin_at:
        open_day = open_checkin_at[:10]
        if open_day == day:
            open_for_day = open_checkin_at
        elif open_day == yesterday and day == today_prefix():
            day_events = [{"direction": "check-in", "timestamp": open_checkin_at, "gate": ""}] + day_events
            open_for_day = open_checkin_at
    return total_work_attendance_minutes(day_events, open_checkin_at=open_for_day)


def total_presence_minutes(events: list[dict[str, Any]]) -> int:
    total = 0
    for session in pair_presence_sessions(events):
        minutes = session.get("durationMinutes")
        if isinstance(minutes, int) and minutes > 0:
            total += minutes
    return total


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


def parse_geofence_id_from_note(note: str | None) -> str:
    match = re.search(r"geofenceId=([^\s;,|]+)", str(note or ""))
    return str(match.group(1)).strip() if match else ""


def parse_device_coords_from_note(note: str | None) -> dict[str, float] | None:
    text = str(note or "")
    lat_match = re.search(r"deviceLat=(-?\d+(?:\.\d+)?)", text)
    lng_match = re.search(r"deviceLng=(-?\d+(?:\.\d+)?)", text)
    if not lat_match or not lng_match:
        return None
    try:
        lat = float(lat_match.group(1))
        lng = float(lng_match.group(1))
    except (TypeError, ValueError):
        return None
    if is_usable_map_coordinate(lat, lng):
        return {"lat": lat, "lng": lng}
    return None


def is_usable_map_coordinate(lat: Any, lng: Any) -> bool:
    try:
        la = float(lat)
        ln = float(lng)
    except (TypeError, ValueError):
        return False
    if not (-90.0 <= la <= 90.0 and -180.0 <= ln <= 180.0):
        return False
    # Reject unset DB defaults and "null island".
    if abs(la) < 0.0001 and abs(ln) < 0.0001:
        return False
    return True


def geofence_by_id(db, company_id: str, geofence_id: str) -> dict[str, Any] | None:
    gid = str(geofence_id or "").strip()
    cid = _cid_param(company_id)
    if not gid or not cid:
        return None
    try:
        row = db.execute(
            """
            SELECT id, site_name, latitude, longitude, radius_meters
            FROM geofences
            WHERE company_id = ? AND id = ? AND active = 1
            LIMIT 1
            """,
            (cid, gid),
        ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def _match_geofence_site(idx: dict[str, dict[str, Any]], site_label: str) -> dict[str, Any] | None:
    key = str(site_label or "").strip()
    if not key or not idx:
        return None
    if key in idx:
        return idx[key]
    folded = key.casefold()
    for name, zone in idx.items():
        name_folded = str(name or "").casefold()
        if not name_folded:
            continue
        if name_folded == folded or name_folded in folded or folded in name_folded:
            return zone
    return None


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
    geofence_id: str = "",
    access_note: str = "",
    seed: str = "",
) -> dict[str, float] | None:
    """Real lat/lng from device GPS note, geofence, worker site, or company geofences."""
    device_coords = parse_device_coords_from_note(access_note)
    if device_coords:
        la, ln = device_coords["lat"], device_coords["lng"]
        if seed:
            la, ln = geo_offset(la, ln, seed)
        return {"lat": la, "lng": ln}

    if is_usable_map_coordinate(lat, lng):
        la, ln = float(lat), float(lng)
        if seed:
            la, ln = geo_offset(la, ln, seed)
        return {"lat": la, "lng": ln}

    zone = geofence_by_id(db, company_id, geofence_id)
    if zone and is_usable_map_coordinate(zone.get("latitude"), zone.get("longitude")):
        la, ln = float(zone["latitude"]), float(zone["longitude"])
        if seed:
            la, ln = geo_offset(la, ln, seed)
        return {"lat": la, "lng": ln}

    idx = geofence_site_index(db, company_id)
    matched = _match_geofence_site(idx, site)
    if matched and is_usable_map_coordinate(matched.get("latitude"), matched.get("longitude")):
        la, ln = float(matched["latitude"]), float(matched["longitude"])
        if seed:
            la, ln = geo_offset(la, ln, seed)
        return {"lat": la, "lng": ln}

    if idx:
        first = next(iter(idx.values()))
        if is_usable_map_coordinate(first.get("latitude"), first.get("longitude")):
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
               COALESCE(latest.timestamp, '') AS last_access,
               COALESCE(latest.note, '') AS last_note
        FROM workers w
        LEFT JOIN (
            SELECT al.worker_id, al.direction, al.gate, al.timestamp, al.note
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
