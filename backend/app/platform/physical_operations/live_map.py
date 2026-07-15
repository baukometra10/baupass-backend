"""Live ops map — geofences, on-site workers, gates, open alerts."""
from __future__ import annotations

from typing import Any

from ._common import (
    geofence_site_index,
    list_on_site_workers,
    parse_geofence_id_from_note,
    resolve_map_coordinates,
    today_prefix,
)


def build_live_ops_map(db, company_id: str) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    today = today_prefix()
    geofences: list[dict[str, Any]] = []
    try:
        rows = db.execute(
            """
            SELECT id, site_name, latitude, longitude, radius_meters, active
            FROM geofences WHERE company_id = ? AND active = 1
            ORDER BY site_name
            """,
            (cid,),
        ).fetchall()
        geofences = [dict(r) for r in rows]
    except Exception:
        pass

    site_coords = geofence_site_index(db, cid)

    workers: list[dict[str, Any]] = []
    for w in list_on_site_workers(db, cid, today):
        last_note = str(w.get("last_note") or "")
        coords = resolve_map_coordinates(
            db,
            cid,
            lat=w.get("site_latitude"),
            lng=w.get("site_longitude"),
            site=str(w.get("site") or ""),
            geofence_id=parse_geofence_id_from_note(last_note),
            access_note=last_note,
            seed=str(w.get("id") or ""),
        )
        if not coords:
            continue
        workers.append(
            {
                "id": w.get("id"),
                "name": f"{w.get('first_name', '')} {w.get('last_name', '')}".strip(),
                "site": w.get("site"),
                "gate": w.get("gate"),
                "lastAccess": w.get("last_access"),
                "lat": coords["lat"],
                "lng": coords["lng"],
            }
        )

    gates: list[dict[str, Any]] = []
    try:
        rows = db.execute(
            """
            SELECT DISTINCT TRIM(al.gate) AS gate, MAX(al.timestamp) AS last_at
            FROM access_logs al
            JOIN workers w ON w.id = al.worker_id
            WHERE w.company_id = ? AND al.timestamp LIKE ? AND TRIM(COALESCE(al.gate, '')) <> ''
            GROUP BY TRIM(al.gate)
            ORDER BY last_at DESC
            LIMIT 20
            """,
            (cid, f"{today}%"),
        ).fetchall()
        for r in rows:
            gate = r["gate"] or "Gate"
            coords = resolve_map_coordinates(db, cid, site=gate, seed=gate)
            if not coords and geofences:
                anchor = geofences[0]
                if anchor.get("latitude") is not None and anchor.get("longitude") is not None:
                    coords = resolve_map_coordinates(
                        db,
                        cid,
                        lat=anchor.get("latitude"),
                        lng=anchor.get("longitude"),
                        seed=gate,
                    )
            if not coords:
                continue
            gates.append(
                {"name": gate, "lat": coords["lat"], "lng": coords["lng"], "lastAt": r["last_at"]}
            )
    except Exception:
        pass

    alerts: list[dict[str, Any]] = []
    try:
        rows = db.execute(
            """
            SELECT id, severity, title, alert_type, created_at
            FROM security_alerts
            WHERE CAST(company_id AS TEXT) = ? AND status = 'open'
            ORDER BY created_at DESC LIMIT 15
            """,
            (cid,),
        ).fetchall()
        alerts = [dict(r) for r in rows]
    except Exception:
        pass

    center = None
    if geofences:
        center = {"lat": float(geofences[0]["latitude"]), "lng": float(geofences[0]["longitude"])}

    return {
        "companyId": cid,
        "date": today,
        "center": center,
        "mapConfigured": bool(geofences),
        "geofences": geofences,
        "workersOnSite": workers,
        "gates": gates,
        "openSecurityAlerts": len(alerts),
        "alerts": alerts,
        "counts": {
            "zones": len(geofences),
            "onSite": len(workers),
            "gates": len(gates),
        },
    }
