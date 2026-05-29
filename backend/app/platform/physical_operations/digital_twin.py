"""Digital Twin — live site map: workers, gates, equipment, hazards, movement."""
from __future__ import annotations

from typing import Any

from ._common import (
    count_on_site,
    geofence_site_index,
    list_on_site_workers,
    resolve_map_coordinates,
    today_prefix,
)


def _gate_positions(db, company_id: str) -> list[dict]:
    rows = db.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(al.gate), ''), 'Gate') AS gate_id,
               COUNT(*) AS events_24h,
               MAX(al.timestamp) AS last_event
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND al.timestamp >= datetime('now', '-1 day')
        GROUP BY gate_id
        ORDER BY events_24h DESC
        LIMIT 50
        """,
        (company_id,),
    ).fetchall()
    gf = geofence_site_index(db, company_id)
    gates = []
    for r in rows:
        gate = r["gate_id"]
        item: dict[str, Any] = {
            "id": gate,
            "label": gate,
            "type": "gate",
            "events24h": int(r["events_24h"] or 0),
            "lastEvent": r["last_event"],
        }
        coords = resolve_map_coordinates(db, company_id, site=gate, seed=gate)
        if not coords and gf:
            coords = resolve_map_coordinates(db, company_id, seed=gate)
        if coords:
            item["map"] = coords
        gates.append(item)
    return gates


def _equipment(db, company_id: str) -> list[dict]:
    try:
        rows = db.execute(
            "SELECT * FROM site_equipment WHERE company_id = ? AND status = 'active'",
            (company_id,),
        ).fetchall()
    except Exception:
        return []
    out = []
    for r in rows:
        item = dict(r)
        coords = resolve_map_coordinates(
            db,
            company_id,
            lat=item.get("latitude"),
            lng=item.get("longitude"),
            site=str(item.get("site") or item.get("name") or ""),
            seed=str(item.get("id") or ""),
        )
        if coords:
            item["map"] = coords
        out.append(item)
    return out


def _hazards(db, company_id: str) -> list[dict]:
    hazards: list[dict] = []
    try:
        rows = db.execute(
            "SELECT * FROM site_hazard_zones WHERE company_id = ? AND active = 1",
            (company_id,),
        ).fetchall()
        hazards.extend(dict(r) for r in rows)
    except Exception:
        pass
    gf = db.execute(
        "SELECT id, site_name AS label, latitude, longitude, radius_meters, active FROM geofences WHERE company_id = ? AND active = 1",
        (str(company_id),),
    ).fetchall()
    for r in gf:
        hazards.append(
            {
                "id": r["id"],
                "label": r["label"],
                "hazard_level": "low",
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "radius_meters": r["radius_meters"],
                "source": "geofence",
            }
        )
    return hazards


def build_digital_twin(db, company_id: str) -> dict[str, Any]:
    today = today_prefix()
    on_site = list_on_site_workers(db, company_id, today)
    workers_entities = []
    for w in on_site:
        site = (w.get("site") or "").strip()
        ent: dict[str, Any] = {
            "id": w["id"],
            "name": f"{w.get('first_name', '')} {w.get('last_name', '')}".strip(),
            "site": site,
            "gate": w.get("gate"),
            "lastAccess": w.get("last_access"),
            "badgeId": w.get("badge_id"),
            "status": w.get("status"),
            "movement": "on_site",
        }
        coords = resolve_map_coordinates(
            db,
            company_id,
            lat=w.get("site_latitude"),
            lng=w.get("site_longitude"),
            site=site,
            seed=str(w.get("id") or ""),
        )
        if coords:
            ent["map"] = coords
        workers_entities.append(ent)
    recent = db.execute(
        """
        SELECT al.worker_id, al.direction, al.gate, al.timestamp,
               w.first_name, w.last_name
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND al.timestamp >= datetime('now', '-15 minutes')
        ORDER BY al.timestamp DESC
        LIMIT 40
        """,
        (company_id,),
    ).fetchall()
    return {
        "layer": "digital_twin",
        "status": "live",
        "company_id": company_id,
        "date": today,
        "summary": {
            "workersOnSite": count_on_site(db, company_id, today),
            "gatesActive": len(_gate_positions(db, company_id)),
            "equipmentCount": len(_equipment(db, company_id)),
            "hazardZones": len(_hazards(db, company_id)),
        },
        "entities": {
            "workers": workers_entities,
            "gates": _gate_positions(db, company_id),
            "equipment": _equipment(db, company_id),
            "hazardZones": _hazards(db, company_id),
        },
        "liveMovement": [dict(r) for r in recent],
    }
