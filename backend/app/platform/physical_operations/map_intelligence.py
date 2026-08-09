"""Smart Workforce Map wave-2: nearest worker, zone stats, anomaly rules."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ._common import is_fresh_live_location, is_usable_map_coordinate, now_iso
from .geospatial_optimizer import BoundingBox, GeoPoint, get_optimizer
from .location_trail import normalize_zone_kind

ACTIVITIES = frozenset({"working", "on_break", "on_task"})

# Crowd: at least this many OR half of on-site (whichever higher threshold applies)
ZONE_CROWD_MIN = 5
OFF_SITE_DWELL_SECONDS = 12 * 60
STALE_ALERT_SECONDS = 25 * 60
WRONG_ZONE_DWELL_SECONDS = 20 * 60


def normalize_activity(value: Any) -> str:
    act = str(value or "working").strip().lower()
    if act in {"break", "pause", "paused"}:
        return "on_break"
    if act in {"task", "mission", "job"}:
        return "on_task"
    return act if act in ACTIVITIES else "working"


def display_status(*, geo_status: str, activity: str) -> str:
    """UI status: activity overrides geo when on break/task (unless shift ended)."""
    geo = str(geo_status or "stale")
    act = normalize_activity(activity)
    if geo == "shift_ended":
        return "shift_ended"
    if act == "on_break":
        return "on_break"
    if act == "on_task":
        return "on_task"
    return geo


def compute_zone_stats(
    zones: list[dict[str, Any]],
    workers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_zone: dict[str, dict[str, Any]] = {}
    for z in zones or []:
        zid = str(z.get("id") or "")
        if not zid:
            continue
        by_zone[zid] = {
            "zoneId": zid,
            "name": z.get("site_name") or z.get("name") or zid,
            "kind": normalize_zone_kind(z.get("zone_kind") or z.get("kind")),
            "color": z.get("color") or "",
            "headcount": 0,
            "byStatus": {
                "working": 0,
                "off_site": 0,
                "stale": 0,
                "on_break": 0,
                "on_task": 0,
            },
            "avgDwellMinutes": None,
        }

    unassigned = {
        "zoneId": "",
        "name": "Außerhalb / unbekannt",
        "kind": "other",
        "color": "#94a3b8",
        "headcount": 0,
        "byStatus": {
            "working": 0,
            "off_site": 0,
            "stale": 0,
            "on_break": 0,
            "on_task": 0,
        },
        "avgDwellMinutes": None,
    }

    for w in workers or []:
        status = str(w.get("status") or "working")
        zone = w.get("currentZone") or {}
        zid = str(zone.get("id") or "")
        bucket = by_zone.get(zid) if zid else unassigned
        if bucket is None:
            bucket = unassigned
        bucket["headcount"] += 1
        if status in bucket["byStatus"]:
            bucket["byStatus"][status] += 1
        else:
            bucket["byStatus"]["working"] += 1

    out = list(by_zone.values())
    if unassigned["headcount"]:
        out.append(unassigned)
    out.sort(key=lambda r: (-int(r["headcount"]), str(r["name"])))
    return out


def find_nearest_workers(
    workers: list[dict[str, Any]],
    *,
    lat: float,
    lng: float,
    limit: int = 5,
    role_query: str = "",
    exclude_break: bool = True,
    radius_meters: float | None = None,
    return_meta: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], dict[str, Any]]:
    """Nearest workers via spatial grid / bbox prune, then Haversine refine."""
    empty_meta = {
        "totalConsidered": 0,
        "bboxFiltered": 0,
        "haversineComputed": 0,
        "cacheHit": False,
        "elapsedMs": 0.0,
        "method": "none",
        "radiusMeters": 0,
        "bbox": None,
    }
    if not is_usable_map_coordinate(lat, lng):
        return ([], empty_meta) if return_meta else []

    q = str(role_query or "").strip().casefold()
    radius = float(radius_meters) if radius_meters is not None else 50_000.0
    radius = max(1.0, min(radius, 200_000.0))

    def filter_fn(w: dict[str, Any]) -> bool:
        status = str(w.get("status") or "")
        activity = normalize_activity(w.get("activity"))
        if exclude_break and (status == "on_break" or activity == "on_break"):
            return False
        if status in {"shift_ended"}:
            return False
        if w.get("lat") is None or w.get("lng") is None:
            return False
        try:
            wlat = float(w["lat"])
            wlng = float(w["lng"])
        except (TypeError, ValueError):
            return False
        if not is_usable_map_coordinate(wlat, wlng):
            return False
        if q:
            role = str(w.get("role") or "")
            site = str(w.get("site") or "")
            zone_name = str((w.get("currentZone") or {}).get("name") or "")
            hay = f"{role} {site} {zone_name} {w.get('name') or ''}".casefold()
            if q not in hay:
                return False
        return True

    result = get_optimizer().find_nearest(
        GeoPoint(float(lat), float(lng), id="search_center"),
        list(workers or []),
        limit=max(1, min(int(limit or 5), 20)),
        radius_meters=radius,
        filter_fn=filter_fn,
        use_grid=True,
        lat_key="lat",
        lng_key="lng",
    )
    ranked: list[dict[str, Any]] = []
    for w in result.points:
        try:
            wlat = float(w["lat"])
            wlng = float(w["lng"])
        except (TypeError, ValueError, KeyError):
            continue
        ranked.append(
            {
                "id": w.get("id"),
                "name": w.get("name"),
                "role": str(w.get("role") or ""),
                "status": str(w.get("status") or ""),
                "activity": normalize_activity(w.get("activity")),
                "lat": wlat,
                "lng": wlng,
                "distanceMeters": int(w.get("distanceMeters") or 0),
                "currentZone": w.get("currentZone"),
                "positionSource": w.get("positionSource"),
            }
        )
    meta = {
        **result.to_meta(),
        "radiusMeters": int(round(radius)),
        "bbox": BoundingBox.around_point(float(lat), float(lng), radius).to_dict(),
    }
    if return_meta:
        return ranked, meta
    return ranked


def _age_seconds(iso_ts: Any) -> float | None:
    text = str(iso_ts or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
    except Exception:
        return None


def _site_suggests_kind(site: str, zone_kind: str, zone_name: str) -> bool:
    """Loose match: worker.site vs zone kind/name — True if compatible or unknown."""
    site_l = str(site or "").casefold()
    kind = normalize_zone_kind(zone_kind)
    name_l = str(zone_name or "").casefold()
    if not site_l:
        return True
    kind_tokens = {
        "production": ("prod", "produktion", "fertigung", "halle", "werk"),
        "warehouse": ("lager", "warehouse", "logistik", "depot"),
        "admin": ("admin", "büro", "buero", "verwaltung", "office"),
        "maintenance": ("wartung", "maintenance", "technik", "instand"),
        "lab": ("labor", "lab", "prüfung", "pruefung"),
    }
    tokens = kind_tokens.get(kind, ())
    if any(t in site_l for t in tokens):
        return True
    if name_l and (name_l in site_l or site_l in name_l):
        return True
    # Site mentions another known kind → likely wrong
    for other, toks in kind_tokens.items():
        if other == kind:
            continue
        if any(t in site_l for t in toks):
            return False
    return True


def evaluate_map_anomalies(
    *,
    company_id: str,
    workers: list[dict[str, Any]],
    zone_stats: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return anomaly descriptors (not yet persisted)."""
    cid = str(company_id or "").strip()
    on_site_n = len(workers or [])
    anomalies: list[dict[str, Any]] = []

    crowd_threshold = max(ZONE_CROWD_MIN, int(round(on_site_n * 0.5)) if on_site_n >= 6 else ZONE_CROWD_MIN)
    for zs in zone_stats or []:
        zid = str(zs.get("zoneId") or "")
        if not zid:
            continue
        hc = int(zs.get("headcount") or 0)
        if hc >= crowd_threshold and hc >= 3:
            anomalies.append(
                {
                    "code": "map.zone_crowd",
                    "severity": "warning",
                    "message": f"Ungewöhnlich viele Personen in Zone „{zs.get('name') or zid}“ ({hc})",
                    "details": {
                        "companyId": cid,
                        "zoneId": zid,
                        "zoneName": zs.get("name"),
                        "zoneKind": zs.get("kind"),
                        "headcount": hc,
                        "threshold": crowd_threshold,
                    },
                }
            )

    for w in workers or []:
        wid = str(w.get("id") or "")
        name = str(w.get("name") or wid)
        status = str(w.get("status") or "")
        age = _age_seconds(w.get("lastLocationAt") or w.get("lastAccess"))
        if status == "off_site" and age is not None and age >= OFF_SITE_DWELL_SECONDS:
            anomalies.append(
                {
                    "code": "map.off_site_dwell",
                    "severity": "warning",
                    "message": f"{name} seit längerem außerhalb der Zone (eingecheckt)",
                    "details": {
                        "companyId": cid,
                        "workerId": wid,
                        "workerName": name,
                        "status": status,
                        "ageSeconds": int(age),
                        "lat": w.get("lat"),
                        "lng": w.get("lng"),
                    },
                }
            )
        if status == "stale" and age is not None and age >= STALE_ALERT_SECONDS:
            anomalies.append(
                {
                    "code": "map.stale_presence",
                    "severity": "info",
                    "message": f"{name}: kein frisches GPS (letzter Standort behalten)",
                    "details": {
                        "companyId": cid,
                        "workerId": wid,
                        "workerName": name,
                        "ageSeconds": int(age),
                        "lat": w.get("lat"),
                        "lng": w.get("lng"),
                    },
                }
            )
        zone = w.get("currentZone") or {}
        if zone.get("id") and status in {"working", "on_task", "on_break"}:
            ok = _site_suggests_kind(
                str(w.get("site") or ""),
                str(zone.get("kind") or ""),
                str(zone.get("name") or ""),
            )
            if not ok and age is not None and age >= WRONG_ZONE_DWELL_SECONDS:
                anomalies.append(
                    {
                        "code": "map.wrong_zone_dwell",
                        "severity": "warning",
                        "message": (
                            f"{name} länger in Zone „{zone.get('name')}“ "
                            f"(Zuordnung: {w.get('site') or '—'})"
                        ),
                        "details": {
                            "companyId": cid,
                            "workerId": wid,
                            "workerName": name,
                            "zoneId": zone.get("id"),
                            "zoneName": zone.get("name"),
                            "zoneKind": zone.get("kind"),
                            "assignedSite": w.get("site"),
                            "ageSeconds": int(age),
                        },
                    }
                )
    return anomalies


def persist_map_anomalies(db, anomalies: list[dict[str, Any]]) -> list[str]:
    """Write anomalies into system_alerts with dedup."""
    created: list[str] = []
    if not anomalies:
        return created
    try:
        from backend.server import create_system_alert
    except Exception:
        return created
    for a in anomalies:
        details = a.get("details") or {}
        # Dedup key in message already; also pass company in details
        alert_id = create_system_alert(
            db,
            str(a.get("code") or "map.anomaly"),
            str(a.get("severity") or "warning"),
            str(a.get("message") or "Karten-Anomalie"),
            details=details if isinstance(details, dict) else {"raw": details},
            dedup_minutes=45,
        )
        if alert_id:
            created.append(str(alert_id))
            try:
                from backend.app.platform.inbox.events import notify_inbox_changed

                cid = str((details or {}).get("companyId") or "")
                if cid:
                    notify_inbox_changed(cid, source="smart_map")
            except Exception:
                pass
    return created


def zone_dwell_averages(db, company_id: str, zone_ids: list[str]) -> dict[str, float]:
    """Rough avg minutes spent in zone today from trail sample spans per worker."""
    cid = str(company_id or "").strip()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out: dict[str, float] = {}

    def _parse(ts: str) -> datetime | None:
        text = str(ts or "").strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    for zid in zone_ids:
        if not zid:
            continue
        try:
            rows = db.execute(
                """
                SELECT worker_id, recorded_at FROM worker_location_samples
                WHERE company_id = ? AND geofence_id = ? AND recorded_at LIKE ?
                ORDER BY worker_id, recorded_at
                """,
                (cid, zid, f"{today}%"),
            ).fetchall()
        except Exception:
            continue
        spans: list[float] = []
        by_worker: dict[str, list[datetime]] = {}
        for r in rows:
            wid = str(r["worker_id"] if hasattr(r, "keys") else r[0])
            at = _parse(str(r["recorded_at"] if hasattr(r, "keys") else r[1]))
            if at:
                by_worker.setdefault(wid, []).append(at)
        for stamps in by_worker.values():
            if len(stamps) < 2:
                continue
            minutes = (stamps[-1] - stamps[0]).total_seconds() / 60.0
            if minutes > 0:
                spans.append(minutes)
        if spans:
            out[zid] = round(sum(spans) / len(spans), 1)
    return out
