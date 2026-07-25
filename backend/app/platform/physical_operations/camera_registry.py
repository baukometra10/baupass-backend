"""Site camera registry — CRUD, heartbeat, live snapshot, health status."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from ._common import now_iso

CAMERA_ONLINE_THRESHOLD_SECONDS = max(
    30, int(os.getenv("BAUPASS_CAMERA_ONLINE_THRESHOLD_SECONDS", "180"))
)
CAMERA_SNAPSHOT_MAX_BYTES = max(50_000, int(os.getenv("BAUPASS_CAMERA_SNAPSHOT_MAX_BYTES", "350000")))


def _table_missing_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "no such table" in msg or "does not exist" in msg


def _parse_last_seen(last_seen: str) -> datetime | None:
    raw = str(last_seen or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def camera_is_online(last_seen_at: str | None, *, threshold: int | None = None) -> bool:
    limit = threshold if threshold is not None else CAMERA_ONLINE_THRESHOLD_SECONDS
    dt = _parse_last_seen(str(last_seen_at or ""))
    if not dt:
        return False
    return (datetime.now(timezone.utc) - dt).total_seconds() <= limit


def _trim_snapshot_b64(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("data:"):
        comma = raw.find(",")
        raw = raw[comma + 1 :] if comma >= 0 else raw
    try:
        import base64

        data = base64.b64decode(raw, validate=False)
        if len(data) > CAMERA_SNAPSHOT_MAX_BYTES:
            return ""
        return base64.b64encode(data).decode("ascii")
    except Exception:
        return ""


def _row_has(row, key: str) -> bool:
    try:
        return key in row.keys()
    except Exception:
        return False


def serialize_camera(row) -> dict[str, Any]:
    last_seen = str(row["last_seen_at"] or "")
    online = camera_is_online(last_seen)
    has_snapshot = bool(str(row["last_snapshot_at"] or "").strip())
    zone_name = str(row["zone_name"] if _row_has(row, "zone_name") else "") or ""
    zone_crit = bool(int(row["zone_critical_only_after_hours"] if _row_has(row, "zone_critical_only_after_hours") else 0) or 0)
    try:
        min_conf = float(row["min_confidence"]) if _row_has(row, "min_confidence") and row["min_confidence"] is not None else 0.0
    except Exception:
        min_conf = 0.0
    lat = None
    lng = None
    if _row_has(row, "latitude") and row["latitude"] is not None:
        try:
            lat = float(row["latitude"])
        except Exception:
            lat = None
    if _row_has(row, "longitude") and row["longitude"] is not None:
        try:
            lng = float(row["longitude"])
        except Exception:
            lng = None
    return {
        "id": row["id"],
        "companyId": row["company_id"],
        "name": row["name"],
        "location": row["location"] or "",
        "rtspUrl": row["rtsp_url"] or "",
        "status": "online" if online else ("offline" if last_seen else "unknown"),
        "online": online,
        "lastSeenAt": last_seen or None,
        "lastSnapshotAt": str(row["last_snapshot_at"] or "") or None,
        "hasSnapshot": has_snapshot,
        "healthError": str(row["health_error"] or ""),
        "zoneName": zone_name,
        "zoneCriticalOnlyAfterHours": zone_crit,
        "minConfidence": min_conf,
        "latitude": lat,
        "longitude": lng,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def list_cameras(db, company_id: str) -> list[dict[str, Any]]:
    try:
        rows = db.execute(
            """
            SELECT * FROM site_cameras
            WHERE company_id = ?
            ORDER BY name COLLATE NOCASE, id
            """,
            (str(company_id),),
        ).fetchall()
        return [serialize_camera(r) for r in rows]
    except Exception as exc:
        if _table_missing_error(exc):
            return []
        raise


def get_camera(db, company_id: str, camera_id: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT * FROM site_cameras WHERE company_id = ? AND id = ?",
        (str(company_id), str(camera_id)),
    ).fetchone()
    return serialize_camera(row) if row else None


def get_camera_snapshot_b64(db, company_id: str, camera_id: str) -> str | None:
    row = db.execute(
        "SELECT last_snapshot_b64 FROM site_cameras WHERE company_id = ? AND id = ?",
        (str(company_id), str(camera_id)),
    ).fetchone()
    if not row:
        return None
    data = str(row["last_snapshot_b64"] or "").strip()
    return data or None


def _slug_camera_id(name: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    slug = slug[:40] or "camera"
    return f"cam-{slug}"


def parse_camera_bulk_text(text: str) -> list[dict[str, Any]]:
    """Parse bulk camera lines: name,location,rtsp (comma/semicolon/tab)."""
    items: list[dict[str, Any]] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ";" in line and "," not in line:
            parts = [p.strip() for p in line.split(";")]
        elif "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        else:
            parts = [p.strip() for p in line.split(",")]
        while len(parts) < 3:
            parts.append("")
        name, location, rtsp_url = parts[0], parts[1], parts[2]
        if not name:
            continue
        item: dict[str, Any] = {
            "name": name,
            "location": location,
            "rtspUrl": rtsp_url,
        }
        if parts[0] and len(parts) >= 4 and parts[3]:
            item["id"] = parts[3]
        else:
            item["id"] = _slug_camera_id(name)
        items.append(item)
    return items


def bulk_create_cameras(db, company_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    created: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, item in enumerate(items or []):
        if not isinstance(item, dict):
            failed.append({"index": index, "error": "invalid_item"})
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            failed.append({"index": index, "error": "name_required"})
            continue
        cam_id = str(item.get("id") or _slug_camera_id(name)).strip()
        if cam_id in used_ids:
            base = cam_id
            suffix = 2
            while f"{base}-{suffix}" in used_ids:
                suffix += 1
            cam_id = f"{base}-{suffix}"
        used_ids.add(cam_id)
        payload = {
            "id": cam_id,
            "name": name,
            "location": str(item.get("location") or "").strip(),
            "rtspUrl": str(item.get("rtspUrl") or item.get("rtsp_url") or "").strip(),
        }
        try:
            existing = get_camera(db, company_id, cam_id)
            if existing:
                row = update_camera(db, company_id, cam_id, payload)
                if row:
                    updated.append(row)
                else:
                    failed.append({"index": index, "error": "update_failed", "name": name})
            else:
                created.append(create_camera(db, company_id, payload))
        except ValueError as exc:
            failed.append({"index": index, "error": str(exc), "name": name})
        except Exception as exc:
            failed.append({"index": index, "error": str(exc), "name": name})
    return {
        "ok": True,
        "created": len(created),
        "updated": len(updated),
        "failed": failed,
        "cameras": created + updated,
    }


def _extract_zone_fields(payload: dict[str, Any], row=None) -> tuple[str, int, float, float | None, float | None]:
    def _cur(key_snake: str, *alts: str, default: Any = None):
        for k in (key_snake, *alts):
            if k in payload:
                return payload.get(k)
        if row is not None and _row_has(row, key_snake):
            return row[key_snake]
        return default

    zone_name = str(_cur("zone_name", "zoneName", default="") or "").strip()[:120]
    zone_crit_raw = _cur("zone_critical_only_after_hours", "zoneCriticalOnlyAfterHours", default=0)
    if isinstance(zone_crit_raw, str):
        zone_crit = 1 if zone_crit_raw.strip().lower() in {"1", "true", "yes", "on"} else 0
    else:
        zone_crit = 1 if zone_crit_raw else 0
    try:
        min_conf = float(_cur("min_confidence", "minConfidence", default=0) or 0)
    except Exception:
        min_conf = 0.0
    min_conf = max(0.0, min(1.0, min_conf))
    lat = _cur("latitude", default=None)
    lng = _cur("longitude", default=None)
    try:
        lat_f = float(lat) if lat is not None and str(lat).strip() != "" else None
    except Exception:
        lat_f = None
    try:
        lng_f = float(lng) if lng is not None and str(lng).strip() != "" else None
    except Exception:
        lng_f = None
    return zone_name, zone_crit, min_conf, lat_f, lng_f


def create_camera(db, company_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("name_required")
    cam_id = str(payload.get("id") or f"cam-{uuid.uuid4().hex[:10]}").strip()
    ts = now_iso()
    location = str(payload.get("location") or "").strip()
    rtsp_url = str(payload.get("rtspUrl") or payload.get("rtsp_url") or "").strip()
    zone_name, zone_crit, min_conf, lat_f, lng_f = _extract_zone_fields(payload)
    try:
        db.execute(
            """
            INSERT INTO site_cameras
                (id, company_id, name, location, rtsp_url, status, last_seen_at,
                 last_snapshot_at, last_snapshot_b64, health_error, offline_alert_sent_at,
                 zone_name, zone_critical_only_after_hours, min_confidence, latitude, longitude,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'unknown', NULL, NULL, '', '', NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cam_id,
                str(company_id),
                name,
                location,
                rtsp_url,
                zone_name,
                zone_crit,
                min_conf,
                lat_f,
                lng_f,
                ts,
                ts,
            ),
        )
        db.commit()
    except Exception:
        db.execute(
            """
            INSERT INTO site_cameras
                (id, company_id, name, location, rtsp_url, status, last_seen_at,
                 last_snapshot_at, last_snapshot_b64, health_error, offline_alert_sent_at,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'unknown', NULL, NULL, '', '', NULL, ?, ?)
            """,
            (cam_id, str(company_id), name, location, rtsp_url, ts, ts),
        )
        db.commit()
    return get_camera(db, company_id, cam_id) or {"id": cam_id}


def update_camera(db, company_id: str, camera_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT * FROM site_cameras WHERE company_id = ? AND id = ?",
        (str(company_id), str(camera_id)),
    ).fetchone()
    if not row:
        return None
    name = str(payload.get("name") if "name" in payload else row["name"]).strip()
    location = str(payload.get("location") if "location" in payload else row["location"] or "").strip()
    rtsp_url = str(
        payload.get("rtspUrl") if "rtspUrl" in payload else payload.get("rtsp_url", row["rtsp_url"] or "")
    ).strip()
    zone_name, zone_crit, min_conf, lat_f, lng_f = _extract_zone_fields(payload, row)
    try:
        db.execute(
            """
            UPDATE site_cameras
            SET name = ?, location = ?, rtsp_url = ?,
                zone_name = ?, zone_critical_only_after_hours = ?, min_confidence = ?,
                latitude = ?, longitude = ?, updated_at = ?
            WHERE company_id = ? AND id = ?
            """,
            (
                name,
                location,
                rtsp_url,
                zone_name,
                zone_crit,
                min_conf,
                lat_f,
                lng_f,
                now_iso(),
                str(company_id),
                str(camera_id),
            ),
        )
        db.commit()
    except Exception:
        db.execute(
            """
            UPDATE site_cameras
            SET name = ?, location = ?, rtsp_url = ?, updated_at = ?
            WHERE company_id = ? AND id = ?
            """,
            (name, location, rtsp_url, now_iso(), str(company_id), str(camera_id)),
        )
        db.commit()
    return get_camera(db, company_id, camera_id)


def delete_camera(db, company_id: str, camera_id: str) -> bool:
    cur = db.execute(
        "DELETE FROM site_cameras WHERE company_id = ? AND id = ?",
        (str(company_id), str(camera_id)),
    )
    db.commit()
    return int(getattr(cur, "rowcount", 0) or 0) > 0


def touch_camera_heartbeat(
    db,
    company_id: str,
    camera_id: str,
    *,
    payload: dict[str, Any] | None = None,
    snapshot_b64: str | None = None,
    health_error: str = "",
) -> dict[str, Any]:
    """Upsert camera row and refresh last_seen / optional snapshot."""
    payload = payload or {}
    cam_id = str(camera_id or payload.get("camera_id") or "unknown").strip() or "unknown"
    company_id = str(company_id)
    ts = now_iso()
    name = str(payload.get("camera_name") or payload.get("name") or cam_id).strip() or cam_id
    location = str(payload.get("location") or payload.get("site") or "").strip()
    rtsp_url = str(payload.get("rtsp_url") or payload.get("rtspUrl") or "").strip()
    snap = _trim_snapshot_b64(snapshot_b64 or payload.get("image_base64") or payload.get("snapshot_base64"))
    row = db.execute(
        "SELECT id, offline_alert_sent_at FROM site_cameras WHERE company_id = ? AND id = ?",
        (company_id, cam_id),
    ).fetchone()
    if row:
        was_offline = bool(str(row["offline_alert_sent_at"] or "").strip())
        db.execute(
            """
            UPDATE site_cameras
            SET last_seen_at = ?, status = 'online', health_error = ?,
                offline_alert_sent_at = CASE WHEN ? != '' THEN NULL ELSE offline_alert_sent_at END,
                last_snapshot_at = CASE WHEN ? != '' THEN ? ELSE last_snapshot_at END,
                last_snapshot_b64 = CASE WHEN ? != '' THEN ? ELSE last_snapshot_b64 END,
                updated_at = ?
            WHERE company_id = ? AND id = ?
            """,
            (
                ts,
                str(health_error or "").strip()[:500],
                snap,
                snap,
                ts,
                snap,
                snap,
                ts,
                company_id,
                cam_id,
            ),
        )
        if was_offline and snap:
            pass  # recovery handled by health job clearing alert flag via NULL above
    else:
        db.execute(
            """
            INSERT INTO site_cameras
                (id, company_id, name, location, rtsp_url, status, last_seen_at,
                 last_snapshot_at, last_snapshot_b64, health_error, offline_alert_sent_at,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'online', ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                cam_id,
                company_id,
                name,
                location,
                rtsp_url,
                ts,
                ts if snap else None,
                snap,
                str(health_error or "").strip()[:500],
                ts,
                ts,
            ),
        )
    db.commit()
    return get_camera(db, company_id, cam_id) or {"id": cam_id, "online": True}
