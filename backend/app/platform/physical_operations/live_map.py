"""Live ops map — geofences, on-site workers, gates, open alerts."""
from __future__ import annotations

from typing import Any

from ._common import (
    geofence_site_index,
    list_on_site_workers,
    resolve_map_coordinates,
    resolve_worker_map_coordinates,
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
        coords = resolve_worker_map_coordinates(db, cid, w)
        if not coords:
            continue
        workers.append(
            {
                "id": w.get("id"),
                "name": f"{w.get('first_name', '')} {w.get('last_name', '')}".strip(),
                "site": w.get("site"),
                "gate": w.get("gate"),
                "lastAccess": w.get("last_access"),
                "lastLocationAt": w.get("last_location_at") or None,
                "positionSource": coords.get("source") or "anchor",
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

    cameras: list[dict[str, Any]] = []
    open_esc_by_cam: dict[str, str] = {}
    try:
        from backend.app.platform.physical_operations.camera_escalation import list_escalations

        for e in list_escalations(db, cid, limit=30, status="open") or []:
            cam_id = str(e.get("cameraId") or "").strip()
            if cam_id and cam_id not in open_esc_by_cam:
                open_esc_by_cam[cam_id] = str(e.get("id") or "")
    except Exception:
        pass
    try:
        from backend.app.platform.physical_operations.camera_registry import list_cameras

        for cam in list_cameras(db, cid) or []:
            lat = cam.get("latitude")
            lng = cam.get("longitude")
            if lat is None or lng is None:
                # Fall back to site/geofence coords so cameras still appear on the map.
                coords = resolve_map_coordinates(
                    db,
                    cid,
                    site=str(cam.get("zoneName") or cam.get("siteKey") or cam.get("name") or ""),
                    seed=str(cam.get("id") or cam.get("name") or "cam"),
                )
                if not coords and geofences:
                    anchor = geofences[0]
                    coords = resolve_map_coordinates(
                        db,
                        cid,
                        lat=anchor.get("latitude"),
                        lng=anchor.get("longitude"),
                        seed=str(cam.get("id") or "cam"),
                    )
                if not coords:
                    continue
                lat, lng = coords["lat"], coords["lng"]
            cam_id = str(cam.get("id") or "")
            esc_id = open_esc_by_cam.get(cam_id) or ""
            cameras.append(
                {
                    "id": cam_id,
                    "name": cam.get("name") or cam_id or "Kamera",
                    "zone": cam.get("zoneName") or cam.get("siteKey") or "",
                    "online": bool(cam.get("online")),
                    "lat": float(lat),
                    "lng": float(lng),
                    "openEscalationId": esc_id or None,
                    "alert": bool(esc_id),
                    "href": (
                        f"/admin-v2/camera-watch.html?company_id={cid}&escalation={esc_id}"
                        if esc_id
                        else f"/admin-v2/camera-watch.html?company_id={cid}"
                    ),
                }
            )
    except Exception:
        cameras = []

    center = None
    if geofences:
        center = {"lat": float(geofences[0]["latitude"]), "lng": float(geofences[0]["longitude"])}
    elif cameras:
        center = {"lat": float(cameras[0]["lat"]), "lng": float(cameras[0]["lng"])}
    elif workers:
        center = {"lat": float(workers[0]["lat"]), "lng": float(workers[0]["lng"])}

    missing_expected = 0
    try:
        from backend.app.platform.physical_operations.daily_brief import build_attendance_brief

        missing_expected = int((build_attendance_brief(db, cid) or {}).get("missingExpected") or 0)
    except Exception:
        missing_expected = 0

    return {
        "companyId": cid,
        "date": today,
        "center": center,
        "mapConfigured": bool(geofences) or bool(cameras),
        "geofences": geofences,
        "workersOnSite": workers,
        "gates": gates,
        "cameras": cameras,
        "openSecurityAlerts": len(alerts),
        "openCameraEscalations": len(open_esc_by_cam),
        "missingExpected": missing_expected,
        "alerts": alerts,
        "autoDial": False,
        "counts": {
            "zones": len(geofences),
            "onSite": len(workers),
            "gates": len(gates),
            "cameras": len(cameras),
            "cameraAlerts": sum(1 for c in cameras if c.get("alert")),
            "missingExpected": missing_expected,
            "security": len(alerts),
        },
    }
