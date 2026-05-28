"""Live ops map — geofences, on-site workers, gates, open alerts."""
from __future__ import annotations

import hashlib
from typing import Any

from ._common import list_on_site_workers, today_prefix


def _offset(lat: float, lng: float, seed: str) -> tuple[float, float]:
    """Spread markers that share the same coordinates."""
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    angle = (h % 360) * 0.0174533
    return lat + 0.00025 * (h % 5) * (1 if h % 2 else -1), lng + 0.00035 * ((h >> 4) % 5) * (1 if (h >> 8) % 2 else -1)


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

    site_coords: dict[str, tuple[float, float]] = {}
    for g in geofences:
        if g.get("latitude") is not None and g.get("longitude") is not None:
            site_coords[str(g.get("site_name") or "")] = (float(g["latitude"]), float(g["longitude"]))

    workers: list[dict[str, Any]] = []
    for w in list_on_site_workers(db, cid, today):
        lat = w.get("site_latitude")
        lng = w.get("site_longitude")
        try:
            if lat is not None and lng is not None:
                lat, lng = float(lat), float(lng)
            else:
                site = str(w.get("site") or "")
                if site in site_coords:
                    lat, lng = site_coords[site]
                elif geofences:
                    lat, lng = float(geofences[0]["latitude"]), float(geofences[0]["longitude"])
                else:
                    continue
            lat, lng = _offset(lat, lng, str(w.get("id") or ""))
            workers.append(
                {
                    "id": w.get("id"),
                    "name": f"{w.get('first_name', '')} {w.get('last_name', '')}".strip(),
                    "site": w.get("site"),
                    "gate": w.get("gate"),
                    "lastAccess": w.get("last_access"),
                    "lat": lat,
                    "lng": lng,
                }
            )
        except (TypeError, ValueError):
            continue

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
        base_lat, base_lng = (geofences[0]["latitude"], geofences[0]["longitude"]) if geofences else (52.52, 13.405)
        for i, r in enumerate(rows):
            gate = r["gate"] or f"Gate {i+1}"
            lat, lng = _offset(float(base_lat), float(base_lng), gate)
            gates.append({"name": gate, "lat": lat, "lng": lng, "lastAt": r["last_at"]})
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

    center = {"lat": 52.52, "lng": 13.405}
    if geofences:
        center = {"lat": float(geofences[0]["latitude"]), "lng": float(geofences[0]["longitude"])}

    return {
        "companyId": cid,
        "date": today,
        "center": center,
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
