"""Live ops map — geofences, on-site workers, gates, open alerts."""
from __future__ import annotations

from typing import Any

from ._common import (
    list_on_site_workers,
    resolve_map_coordinates,
    resolve_worker_map_coordinates,
    today_prefix,
)
from .location_trail import (
    ZONE_KIND_COLORS,
    cameras_for_zone,
    derive_worker_map_status,
    list_active_geofences,
    normalize_zone_kind,
    resolve_containing_zone,
)
from .map_intelligence import (
    compute_zone_stats,
    display_status,
    evaluate_map_anomalies,
    normalize_activity,
    persist_map_anomalies,
    zone_dwell_averages,
)


def build_live_ops_map(db, company_id: str, *, emit_anomalies: bool = True) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    today = today_prefix()
    geofences = list_active_geofences(db, cid)

    workers: list[dict[str, Any]] = []
    status_counts = {"working": 0, "off_site": 0, "stale": 0, "on_break": 0, "on_task": 0}
    for w in list_on_site_workers(db, cid, today):
        coords = resolve_worker_map_coordinates(db, cid, w)
        if not coords:
            continue
        lat = float(coords["lat"])
        lng = float(coords["lng"])
        zone = resolve_containing_zone(lat, lng, geofences)
        inside = zone is not None
        if not geofences:
            inside = True
        position_source = str(coords.get("source") or "anchor")
        geo_status = derive_worker_map_status(
            position_source=position_source,
            last_location_at=w.get("last_location_at"),
            inside_zone=inside,
            has_open_session=True,
        )
        activity = normalize_activity(w.get("activity"))
        status = display_status(geo_status=geo_status, activity=activity)
        if status in status_counts:
            status_counts[status] += 1
        workers.append(
            {
                "id": w.get("id"),
                "name": f"{w.get('first_name', '')} {w.get('last_name', '')}".strip(),
                "badgeId": w.get("badge_id") or "",
                "role": w.get("role") or "",
                "site": w.get("site"),
                "gate": w.get("gate"),
                "lastAccess": w.get("last_access"),
                "lastLocationAt": w.get("last_location_at") or None,
                "positionSource": position_source,
                "geoStatus": geo_status,
                "status": status,
                "activity": activity,
                "activityNote": w.get("activity_note") or "",
                "taskRef": w.get("task_ref") or "",
                "currentZone": (
                    {
                        "id": zone.get("id"),
                        "name": zone.get("site_name"),
                        "kind": zone.get("zone_kind"),
                        "color": zone.get("color"),
                    }
                    if zone
                    else None
                ),
                "lat": lat,
                "lng": lng,
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

    zones_out: list[dict[str, Any]] = []
    for z in geofences:
        kind = normalize_zone_kind(z.get("zone_kind"))
        zone_payload = {
            "id": z.get("id"),
            "site_name": z.get("site_name"),
            "latitude": z.get("latitude"),
            "longitude": z.get("longitude"),
            "radius_meters": z.get("radius_meters"),
            "active": z.get("active"),
            "zone_kind": kind,
            "color": z.get("color") or ZONE_KIND_COLORS.get(kind, "#38bdf8"),
        }
        zone_payload["cameras"] = [
            {"id": c["id"], "name": c["name"], "href": c["href"], "alert": c.get("alert")}
            for c in cameras_for_zone(cameras, zone_payload)
        ]
        zones_out.append(zone_payload)

    center = None
    if zones_out:
        center = {"lat": float(zones_out[0]["latitude"]), "lng": float(zones_out[0]["longitude"])}
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

    zone_stats = compute_zone_stats(zones_out, workers)
    dwell = zone_dwell_averages(db, cid, [str(z.get("id") or "") for z in zones_out])
    for zs in zone_stats:
        zid = str(zs.get("zoneId") or "")
        if zid and zid in dwell:
            zs["avgDwellMinutes"] = dwell[zid]

    anomalies = evaluate_map_anomalies(company_id=cid, workers=workers, zone_stats=zone_stats)
    anomaly_ids: list[str] = []
    if emit_anomalies and anomalies:
        try:
            anomaly_ids = persist_map_anomalies(db, anomalies)
        except Exception:
            anomaly_ids = []

    return {
        "companyId": cid,
        "date": today,
        "center": center,
        "mapConfigured": bool(zones_out) or bool(cameras),
        "geofences": zones_out,
        "smartZones": zones_out,
        "workersOnSite": workers,
        "gates": gates,
        "cameras": cameras,
        "openSecurityAlerts": len(alerts),
        "openCameraEscalations": len(open_esc_by_cam),
        "missingExpected": missing_expected,
        "alerts": alerts,
        "autoDial": False,
        "statusCounts": status_counts,
        "zoneStats": zone_stats,
        "mapAnomalies": [
            {
                "code": a.get("code"),
                "severity": a.get("severity"),
                "message": a.get("message"),
                "details": a.get("details"),
            }
            for a in anomalies[:20]
        ],
        "anomaliesEmitted": anomaly_ids,
        "zoneKinds": sorted(ZONE_KIND_COLORS.keys()),
        "counts": {
            "zones": len(zones_out),
            "onSite": len(workers),
            "working": status_counts["working"],
            "offSite": status_counts["off_site"],
            "stale": status_counts["stale"],
            "onBreak": status_counts["on_break"],
            "onTask": status_counts["on_task"],
            "gates": len(gates),
            "cameras": len(cameras),
            "cameraAlerts": sum(1 for c in cameras if c.get("alert")),
            "missingExpected": missing_expected,
            "security": len(alerts),
            "mapAnomalies": len(anomalies),
        },
    }
