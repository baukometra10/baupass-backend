"""IoT Workforce Infrastructure — device registry + telemetry."""
from __future__ import annotations

import json
import uuid
from typing import Any

from ._common import now_iso


def list_devices(db, company_id: int) -> list[dict]:
    try:
        rows = db.execute(
            "SELECT * FROM iot_devices WHERE company_id = ? ORDER BY device_type, name",
            (company_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def register_device(db, company_id: int, payload: dict[str, Any]) -> dict:
    did = str(payload.get("id") or f"iot-{uuid.uuid4().hex[:10]}")
    db.execute(
        """
        INSERT INTO iot_devices
            (id, company_id, device_type, name, site_name, external_id, status, config_json, last_seen_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, NULL, ?)
        ON CONFLICT(id) DO UPDATE SET
            device_type = excluded.device_type,
            name = excluded.name,
            site_name = excluded.site_name,
            config_json = excluded.config_json
        """,
        (
            did,
            company_id,
            str(payload.get("device_type", "sensor")),
            str(payload.get("name", "Device")),
            str(payload.get("site_name", "")),
            str(payload.get("external_id", "")),
            json.dumps(payload.get("config") or {}),
            now_iso(),
        ),
    )
    db.commit()
    return {"id": did, "status": "registered"}


def record_telemetry(db, device_id: str, company_id: int, payload: dict) -> dict:
    db.execute(
        """
        INSERT INTO iot_telemetry (id, device_id, payload_json, received_at)
        VALUES (?, ?, ?, ?)
        """,
        (f"tel-{uuid.uuid4().hex[:10]}", device_id, json.dumps(payload), now_iso()),
    )
    try:
        db.execute(
            "UPDATE iot_devices SET last_seen_at = ? WHERE id = ? AND company_id = ?",
            (now_iso(), device_id, company_id),
        )
    except Exception:
        pass
    db.commit()
    from backend.app.platform.events.bus import publish_event

    publish_event("iot.telemetry", company_id, {"device_id": device_id, "payload": payload})
    return {"ok": True, "device_id": device_id}


def build_iot_overview(db, company_id: int) -> dict[str, Any]:
    devices = list_devices(db, company_id)
    types: dict[str, int] = {}
    for d in devices:
        t = d.get("device_type", "sensor")
        types[t] = types.get(t, 0) + 1
    recent = []
    try:
        recent = db.execute(
            """
            SELECT t.device_id, t.received_at, t.payload_json
            FROM iot_telemetry t
            JOIN iot_devices d ON d.id = t.device_id
            WHERE d.company_id = ?
            ORDER BY t.received_at DESC LIMIT 20
            """,
            (company_id,),
        ).fetchall()
    except Exception:
        pass
    return {
        "layer": "iot_workforce_infrastructure",
        "devices": devices,
        "devicesByType": types,
        "recentTelemetry": [dict(r) for r in recent],
    }
