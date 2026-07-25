"""NVR vendor webhook normalization → camera event ingest."""
from __future__ import annotations

from typing import Any


def _first(*values: Any) -> Any:
    for v in values:
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return v
    return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _map_event_type(raw: str) -> str:
    s = str(raw or "").strip().lower()
    aliases = {
        "intrusion": "possible_intrusion",
        "intrusiondetection": "possible_intrusion",
        "linedetection": "restricted_area_activity",
        "linedetect": "restricted_area_activity",
        "regionentrance": "restricted_zone",
        "regionexiting": "restricted_zone",
        "fielddetection": "restricted_area_activity",
        "videomotion": "motion",
        "motiondetect": "motion",
        "vmotion": "motion",
        "human": "person",
        "persondetect": "person",
        "facedetection": "person",
        "unattendedbaggage": "possible_intrusion",
        "crossline": "restricted_area_activity",
        "enterarea": "restricted_zone",
        "leavearea": "restricted_zone",
        "forcedentry": "forced_entry",
        "forced_entry": "forced_entry",
        "unknownperson": "unknown_person",
        "tailgating": "tailgating",
    }
    if s in aliases:
        return aliases[s]
    compact = "".join(ch for ch in s if ch.isalnum())
    return aliases.get(compact, s or "motion")


def _parse_hikvision(data: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    event = data.get("EventNotificationAlert") or data.get("eventNotificationAlert") or data
    if not isinstance(event, dict):
        event = data
    channel = _first(
        event.get("channelID"),
        event.get("channelId"),
        event.get("dynChannelID"),
        data.get("channelID"),
        headers.get("X-Channel-Id"),
    )
    camera_id = str(
        _first(
            event.get("camera_id"),
            event.get("cameraId"),
            data.get("camera_id"),
            data.get("cameraId"),
            f"hik-ch-{channel}" if channel is not None else "hikvision",
        )
    )
    event_type = _map_event_type(
        str(
            _first(
                event.get("eventType"),
                event.get("eventState"),
                event.get("eventDescription"),
                data.get("event_type"),
                data.get("type"),
                "motion",
            )
        )
    )
    conf = _as_float(_first(event.get("confidence"), data.get("confidence"), 0.8))
    image = _first(
        event.get("image_base64"),
        event.get("snapshot_base64"),
        data.get("image_base64"),
        data.get("snapshot_base64"),
        data.get("picture"),
    )
    location = str(_first(event.get("location"), data.get("location"), event.get("regionName"), "") or "")
    return {
        "camera_id": camera_id,
        "camera_name": str(_first(event.get("channelName"), data.get("camera_name"), camera_id) or camera_id),
        "event_type": event_type,
        "confidence": conf if conf is not None else 0.8,
        "location": location,
        "site": location,
        "image_base64": str(image or ""),
        "vendor": "hikvision",
        "raw_event_type": str(_first(event.get("eventType"), data.get("eventType"), "") or ""),
    }


def _parse_dahua(data: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    code = str(_first(data.get("Code"), data.get("code"), data.get("event_type"), data.get("type"), "motion") or "motion")
    action = str(_first(data.get("Action"), data.get("action"), "") or "")
    index = _first(data.get("Index"), data.get("index"), data.get("channel"), headers.get("X-Channel-Id"))
    camera_id = str(
        _first(
            data.get("camera_id"),
            data.get("cameraId"),
            f"dahua-ch-{index}" if index is not None else "dahua",
        )
    )
    event_type = _map_event_type(code if code.lower() not in {"videomotion", "motion"} or not action else f"{code}_{action}")
    if str(code).lower() in {"videomotion", "motiondetect", "motion"}:
        event_type = "motion"
    conf = _as_float(_first(data.get("confidence"), data.get("Confidence"), 0.75))
    data_obj = data.get("Data") if isinstance(data.get("Data"), dict) else {}
    image = _first(
        data.get("image_base64"),
        data.get("snapshot_base64"),
        data_obj.get("image_base64") if isinstance(data_obj, dict) else None,
    )
    location = str(_first(data.get("location"), data_obj.get("Name") if isinstance(data_obj, dict) else None, "") or "")
    return {
        "camera_id": camera_id,
        "camera_name": str(_first(data.get("camera_name"), data.get("Name"), camera_id) or camera_id),
        "event_type": event_type,
        "confidence": conf if conf is not None else 0.75,
        "location": location,
        "site": location,
        "image_base64": str(image or ""),
        "vendor": "dahua",
        "raw_event_type": code,
    }


def _parse_generic(data: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    camera_id = str(
        _first(
            data.get("camera_id"),
            data.get("cameraId"),
            data.get("channel"),
            headers.get("X-Camera-Id"),
            "nvr-generic",
        )
    )
    event_type = _map_event_type(
        str(_first(data.get("event_type"), data.get("eventType"), data.get("type"), "motion") or "motion")
    )
    conf = _as_float(_first(data.get("confidence"), data.get("score"), 0.7))
    image = _first(
        data.get("image_base64"),
        data.get("snapshot_base64"),
        data.get("photo_base64"),
        data.get("image"),
    )
    location = str(_first(data.get("location"), data.get("site"), data.get("site_key"), "") or "")
    out = {
        "camera_id": camera_id,
        "camera_name": str(_first(data.get("camera_name"), data.get("cameraName"), camera_id) or camera_id),
        "event_type": event_type,
        "confidence": conf if conf is not None else 0.7,
        "location": location,
        "site": location,
        "image_base64": str(image or ""),
        "vendor": "generic",
    }
    if data.get("clip_base64") or data.get("clipBase64"):
        out["clip_base64"] = str(data.get("clip_base64") or data.get("clipBase64") or "")
    if data.get("worker_id") or data.get("workerId"):
        out["worker_id"] = str(data.get("worker_id") or data.get("workerId"))
    if "in_restricted_zone" in data:
        out["in_restricted_zone"] = data.get("in_restricted_zone")
    if data.get("zone"):
        out["zone"] = data.get("zone")
    return out


def normalize_nvr_payload(vendor: str, data: dict[str, Any] | None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """Normalize vendor webhook payload into ingest_camera_event shape."""
    payload = data if isinstance(data, dict) else {}
    hdrs = {str(k): str(v) for k, v in (headers or {}).items()}
    v = str(vendor or "generic").strip().lower()
    if v in {"hikvision", "hik", "isapi"}:
        return _parse_hikvision(payload, hdrs)
    if v in {"dahua", "dh"}:
        return _parse_dahua(payload, hdrs)
    return _parse_generic(payload, hdrs)


def ingest_nvr_webhook(
    db,
    company_id: str,
    vendor: str,
    data: dict[str, Any] | None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    from backend.app.platform.physical_operations.camera_ai import ingest_camera_event

    company_id = str(company_id or "").strip()
    if not company_id:
        return {"ok": False, "error": "missing_company_id", "autoDial": False}
    normalized = normalize_nvr_payload(vendor, data, headers)
    result = ingest_camera_event(db, company_id, normalized)
    return {
        "ok": True,
        "vendor": str(vendor or "generic").strip().lower(),
        "normalized": {
            "camera_id": normalized.get("camera_id"),
            "event_type": normalized.get("event_type"),
            "confidence": normalized.get("confidence"),
        },
        "autoDial": False,
        **result,
    }
