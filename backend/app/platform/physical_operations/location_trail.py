"""GPS trail samples + smart-zone resolution for Smart Workforce Map."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ._common import is_fresh_live_location, is_usable_map_coordinate, now_iso
from .geospatial_optimizer import (
    haversine_meters,
    point_in_circle_bbox_then_haversine,
)

TRAIL_MIN_INTERVAL_SECONDS = 20
TRAIL_MIN_MOVE_METERS = 10.0
TRAIL_RETENTION_DAYS = 14

ZONE_KINDS = frozenset(
    {"production", "warehouse", "admin", "maintenance", "lab", "other", "site"}
)

ZONE_KIND_COLORS = {
    "production": "#f59e0b",
    "warehouse": "#8b5cf6",
    "admin": "#3b82f6",
    "maintenance": "#ef4444",
    "lab": "#14b8a6",
    "other": "#94a3b8",
    "site": "#38bdf8",
}


def normalize_zone_kind(value: Any) -> str:
    kind = str(value or "site").strip().lower()
    return kind if kind in ZONE_KINDS else "site"

def list_active_geofences(db, company_id: str) -> list[dict[str, Any]]:
    cid = str(company_id or "").strip()
    try:
        rows = db.execute(
            """
            SELECT id, site_name, latitude, longitude, radius_meters, active,
                   COALESCE(zone_kind, 'site') AS zone_kind,
                   COALESCE(color, '') AS color
            FROM geofences
            WHERE company_id = ? AND active = 1
            ORDER BY site_name
            """,
            (cid,),
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["zone_kind"] = normalize_zone_kind(item.get("zone_kind"))
            if not str(item.get("color") or "").strip():
                item["color"] = ZONE_KIND_COLORS.get(item["zone_kind"], "#38bdf8")
            out.append(item)
        return out
    except Exception:
        try:
            rows = db.execute(
                """
                SELECT id, site_name, latitude, longitude, radius_meters, active
                FROM geofences WHERE company_id = ? AND active = 1
                ORDER BY site_name
                """,
                (cid,),
            ).fetchall()
            out = []
            for r in rows:
                item = dict(r)
                item["zone_kind"] = "site"
                item["color"] = ZONE_KIND_COLORS["site"]
                out.append(item)
            return out
        except Exception:
            return []


def resolve_containing_zone(
    lat: float,
    lng: float,
    zones: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Nearest geofence circle that contains the point (bbox reject → Haversine)."""
    best: dict[str, Any] | None = None
    best_dist = float("inf")
    for z in zones or []:
        try:
            zlat = float(z["latitude"])
            zlng = float(z["longitude"])
            radius = float(z.get("radius_meters") or 50)
        except (TypeError, ValueError, KeyError):
            continue
        inside, dist = point_in_circle_bbox_then_haversine(lat, lng, zlat, zlng, radius)
        if not inside or dist is None or dist >= best_dist:
            continue
        best_dist = dist
        kind = normalize_zone_kind(z.get("zone_kind"))
        best = {
            "id": z.get("id"),
            "site_name": z.get("site_name"),
            "zone_kind": kind,
            "color": z.get("color") or ZONE_KIND_COLORS.get(kind, "#38bdf8"),
            "distanceMeters": int(round(dist)),
            "radiusMeters": int(round(radius)),
        }
    return best


def derive_worker_map_status(
    *,
    position_source: str,
    last_location_at: Any,
    inside_zone: bool,
    has_open_session: bool = True,
) -> str:
    """working | off_site | stale | shift_ended."""
    if not has_open_session:
        return "shift_ended"
    source = str(position_source or "").strip().lower()
    fresh = is_fresh_live_location(last_location_at)
    if source == "live" and fresh:
        return "working" if inside_zone else "off_site"
    if source == "live" and not fresh:
        return "stale"
    if source == "checkin":
        return "working" if inside_zone else "stale"
    return "stale"


def maybe_record_location_sample(
    db,
    *,
    worker_id: str,
    company_id: str,
    lat: float,
    lng: float,
    accuracy_m: float | None = None,
    geofence_id: str = "",
    zone_kind: str = "",
    at: str | None = None,
    min_interval_seconds: float = TRAIL_MIN_INTERVAL_SECONDS,
    min_move_meters: float = TRAIL_MIN_MOVE_METERS,
) -> bool:
    """Append a trail point when enough time or distance passed since last sample."""
    if not is_usable_map_coordinate(lat, lng):
        return False
    wid = str(worker_id)
    cid = str(company_id)
    stamp = str(at or "").strip() or now_iso()
    try:
        last = db.execute(
            """
            SELECT lat, lng, recorded_at FROM worker_location_samples
            WHERE worker_id = ?
            ORDER BY recorded_at DESC LIMIT 1
            """,
            (wid,),
        ).fetchone()
    except Exception:
        return False

    if last:
        try:
            prev_at = str(last["recorded_at"] or "")
            text = prev_at[:-1] + "+00:00" if prev_at.endswith("Z") else prev_at
            prev_dt = datetime.fromisoformat(text)
            if prev_dt.tzinfo is None:
                prev_dt = prev_dt.replace(tzinfo=timezone.utc)
            now_dt = datetime.now(timezone.utc)
            try:
                st = stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp
                parsed = datetime.fromisoformat(st)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                now_dt = parsed
            except Exception:
                pass
            age = (now_dt - prev_dt.astimezone(timezone.utc)).total_seconds()
            dist = haversine_meters(float(last["lat"]), float(last["lng"]), float(lat), float(lng))
            if age < min_interval_seconds and dist < min_move_meters:
                return False
        except Exception:
            pass

    sample_id = f"wls-{uuid.uuid4().hex[:16]}"
    try:
        db.execute(
            """
            INSERT INTO worker_location_samples (
                id, worker_id, company_id, lat, lng, accuracy_m,
                geofence_id, zone_kind, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                wid,
                cid,
                float(lat),
                float(lng),
                float(accuracy_m) if accuracy_m is not None else None,
                str(geofence_id or ""),
                normalize_zone_kind(zone_kind) if zone_kind else "",
                stamp,
            ),
        )
        return True
    except Exception:
        return False


def purge_old_location_samples(
    db, *, company_id: str | None = None, retention_days: int = TRAIL_RETENTION_DAYS
) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    try:
        if company_id:
            cur = db.execute(
                "DELETE FROM worker_location_samples WHERE company_id = ? AND recorded_at < ?",
                (str(company_id), cutoff),
            )
        else:
            cur = db.execute(
                "DELETE FROM worker_location_samples WHERE recorded_at < ?",
                (cutoff,),
            )
        return int(cur.rowcount or 0)
    except Exception:
        return 0


def get_worker_trail(
    db,
    *,
    company_id: str,
    worker_id: str,
    from_iso: str | None = None,
    to_iso: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    wid = str(worker_id or "").strip()
    limit = max(1, min(int(limit or 500), 2000))
    from_iso = str(from_iso or "").strip()
    to_iso = str(to_iso or "").strip()
    if not from_iso:
        from_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d") + "T00:00:00.000000Z"
    params: list[Any] = [wid, cid, from_iso]
    where = "worker_id = ? AND company_id = ? AND recorded_at >= ?"
    if to_iso:
        where += " AND recorded_at <= ?"
        params.append(to_iso)
    params.append(limit)
    points: list[dict[str, Any]] = []
    try:
        rows = db.execute(
            f"""
            SELECT id, lat, lng, accuracy_m, geofence_id, zone_kind, recorded_at
            FROM worker_location_samples
            WHERE {where}
            ORDER BY recorded_at ASC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        for r in rows:
            def _g(key, idx, default=None):
                try:
                    if hasattr(r, "keys") and key in r.keys():
                        return r[key]
                except Exception:
                    pass
                try:
                    return r[idx]
                except Exception:
                    return default

            points.append(
                {
                    "id": _g("id", 0, ""),
                    "lat": float(_g("lat", 1)),
                    "lng": float(_g("lng", 2)),
                    "accuracyM": _g("accuracy_m", 3),
                    "geofenceId": _g("geofence_id", 4, "") or "",
                    "zoneKind": _g("zone_kind", 5, "") or "",
                    "at": _g("recorded_at", 6, ""),
                }
            )
    except Exception:
        points = []
    return {
        "workerId": wid,
        "companyId": cid,
        "from": from_iso,
        "to": to_iso or None,
        "count": len(points),
        "points": points,
    }


def cameras_for_zone(
    cameras: list[dict[str, Any]],
    zone: dict[str, Any],
) -> list[dict[str, Any]]:
    """Match cameras by zone name or coordinates inside the geofence circle."""
    site = str(zone.get("site_name") or "").strip().casefold()
    try:
        zlat = float(zone["latitude"])
        zlng = float(zone["longitude"])
        radius = float(zone.get("radius_meters") or 50)
    except (TypeError, ValueError, KeyError):
        zlat = None
        zlng = None
        radius = 0.0
    matched: list[dict[str, Any]] = []
    for cam in cameras or []:
        zone_label = str(cam.get("zone") or cam.get("zoneName") or cam.get("siteKey") or "").strip()
        name_hit = bool(
            site and zone_label and (site in zone_label.casefold() or zone_label.casefold() in site)
        )
        geo_hit = False
        if zlat is not None and cam.get("lat") is not None and cam.get("lng") is not None:
            try:
                inside, _dist = point_in_circle_bbox_then_haversine(
                    float(cam["lat"]), float(cam["lng"]), zlat, zlng, radius
                )
                geo_hit = inside
            except (TypeError, ValueError):
                geo_hit = False
        if name_hit or geo_hit:
            matched.append(cam)
    return matched
