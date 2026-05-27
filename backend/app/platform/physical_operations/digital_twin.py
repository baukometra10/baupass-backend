"""Digital Twin — live site map: workers, gates, equipment, hazards, movement."""
from __future__ import annotations

from typing import Any

from ._common import count_on_site, list_on_site_workers, today_prefix


def _gate_positions(db, company_id: int) -> list[dict]:
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
    gates = []
    for i, r in enumerate(rows):
        gates.append(
            {
                "id": r["gate_id"],
                "label": r["gate_id"],
                "type": "gate",
                "events24h": int(r["events_24h"] or 0),
                "lastEvent": r["last_event"],
                "map": {"x": 20 + (i % 5) * 18, "y": 15 + (i // 5) * 22},
            }
        )
    return gates


def _equipment(db, company_id: int) -> list[dict]:
    try:
        rows = db.execute(
            "SELECT * FROM site_equipment WHERE company_id = ? AND status = 'active'",
            (company_id,),
        ).fetchall()
    except Exception:
        return []
    out = []
    for i, r in enumerate(rows):
        item = dict(r)
        if item.get("latitude") is None:
            item["map"] = {"x": 60 + (i % 4) * 10, "y": 70 + (i // 4) * 8}
        else:
            item["map"] = {"lat": item["latitude"], "lng": item["longitude"]}
        out.append(item)
    return out


def _hazards(db, company_id: int) -> list[dict]:
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


def build_digital_twin(db, company_id: int) -> dict[str, Any]:
    today = today_prefix()
    on_site = list_on_site_workers(db, company_id, today)
    workers_entities = []
    for i, w in enumerate(on_site):
        site = (w.get("site") or "").strip()
        workers_entities.append(
            {
                "id": w["id"],
                "name": f"{w.get('first_name', '')} {w.get('last_name', '')}".strip(),
                "site": site,
                "gate": w.get("gate"),
                "lastAccess": w.get("last_access"),
                "badgeId": w.get("badge_id"),
                "status": w.get("status"),
                "map": {"x": 30 + (i % 6) * 12, "y": 40 + (i // 6) * 10},
                "movement": "on_site",
            }
        )
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
