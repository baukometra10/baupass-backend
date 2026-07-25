"""Cloud vision adapter for after-hours frame analysis (env-gated)."""
from __future__ import annotations

import json
import os
import re
from typing import Any


def vision_enabled() -> bool:
    flag = str(os.getenv("BAUPASS_CAMERA_VISION", "1")).strip().lower()
    if flag in {"0", "false", "off", "no"}:
        return False
    return bool(
        os.getenv("OPENAI_API_KEY")
        or os.getenv("AZURE_OPENAI_API_KEY")
        or os.getenv("BAUPASS_VISION_FORCE_HEURISTIC", "").strip() in {"1", "true", "yes"}
    )


def _heuristic_from_meta(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = meta or {}
    labels: list[str] = []
    if meta.get("motion") or meta.get("has_motion"):
        labels.append("person_detected")
    if meta.get("in_restricted_zone") or meta.get("restricted"):
        labels.append("restricted_area_activity")
    if not labels and meta.get("assume_person"):
        labels.append("person_detected")
        labels.append("possible_intrusion")
    conf = float(meta.get("confidence") or 0.55)
    return {
        "provider": "heuristic",
        "labels": labels or ["activity"],
        "confidence": conf,
        "summary": "Heuristic after-hours frame review (no cloud vision key configured).",
        "personDetected": "person_detected" in labels or "possible_intrusion" in labels,
        "possibleIntrusion": "possible_intrusion" in labels or "restricted_area_activity" in labels,
    }


def _parse_vision_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}


def analyze_snapshot_b64(
    snapshot_b64: str,
    *,
    camera_name: str = "",
    location: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze a JPEG/PNG base64 frame. Falls back to heuristic when no API key."""
    b64 = str(snapshot_b64 or "").strip()
    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[-1]
    if not b64:
        return {
            "provider": "none",
            "labels": [],
            "confidence": 0.0,
            "summary": "No snapshot available",
            "personDetected": False,
            "possibleIntrusion": False,
        }

    if os.getenv("BAUPASS_VISION_FORCE_HEURISTIC", "").strip().lower() in {"1", "true", "yes"}:
        return _heuristic_from_meta({**(meta or {}), "assume_person": True})

    openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    azure_key = (os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
    azure_endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip().rstrip("/")
    azure_deployment = (os.getenv("AZURE_OPENAI_VISION_DEPLOYMENT") or os.getenv("AZURE_OPENAI_DEPLOYMENT") or "").strip()

    prompt = (
        "You are a construction site security reviewer. Look at this camera still. "
        "Reply ONLY JSON with keys: labels (array of strings from "
        "[person_detected, possible_intrusion, restricted_area_activity, vehicle, empty]), "
        "confidence (0-1), summary (short English, no accusation of theft). "
        f"Camera={camera_name or 'unknown'}; location={location or 'site'}."
    )

    try:
        if azure_key and azure_endpoint and azure_deployment:
            import urllib.request

            url = (
                f"{azure_endpoint}/openai/deployments/{azure_deployment}/chat/completions"
                f"?api-version={os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview')}"
            )
            body = {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64[:900000]}"},
                            },
                        ],
                    }
                ],
                "max_tokens": 300,
                "temperature": 0.1,
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json", "api-key": azure_key},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            text = payload["choices"][0]["message"]["content"]
            parsed = _parse_vision_json(text)
            labels = [str(x) for x in (parsed.get("labels") or [])]
            return {
                "provider": "azure_openai",
                "labels": labels,
                "confidence": float(parsed.get("confidence") or 0.6),
                "summary": str(parsed.get("summary") or "Vision review complete"),
                "personDetected": any(l in labels for l in ("person_detected", "possible_intrusion")),
                "possibleIntrusion": any(
                    l in labels for l in ("possible_intrusion", "restricted_area_activity")
                ),
            }
        if openai_key:
            import urllib.request

            body = {
                "model": os.getenv("BAUPASS_VISION_MODEL", "gpt-4o-mini"),
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64[:900000]}"},
                            },
                        ],
                    }
                ],
                "max_tokens": 300,
                "temperature": 0.1,
            }
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {openai_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            text = payload["choices"][0]["message"]["content"]
            parsed = _parse_vision_json(text)
            labels = [str(x) for x in (parsed.get("labels") or [])]
            return {
                "provider": "openai",
                "labels": labels,
                "confidence": float(parsed.get("confidence") or 0.6),
                "summary": str(parsed.get("summary") or "Vision review complete"),
                "personDetected": any(l in labels for l in ("person_detected", "possible_intrusion")),
                "possibleIntrusion": any(
                    l in labels for l in ("possible_intrusion", "restricted_area_activity")
                ),
            }
    except Exception as exc:
        out = _heuristic_from_meta({**(meta or {}), "assume_person": True})
        out["error"] = str(exc)[:200]
        return out

    return _heuristic_from_meta({**(meta or {}), "assume_person": True})


def vision_result_to_event_payload(vision: dict[str, Any], *, camera_id: str, company_id: str) -> dict[str, Any]:
    labels = [str(x) for x in (vision.get("labels") or [])]
    event_type = "motion"
    in_restricted = False
    if "restricted_area_activity" in labels:
        event_type = "restricted_zone"
        in_restricted = True
    elif "possible_intrusion" in labels:
        event_type = "possible_intrusion"
    elif "person_detected" in labels:
        event_type = "unknown_person"
    return {
        "companyId": company_id,
        "camera_id": camera_id,
        "event_type": event_type,
        "confidence": vision.get("confidence"),
        "in_restricted_zone": in_restricted,
        "zone": "after_hours_watch" if in_restricted else "",
        "vision": vision,
        "source": "after_hours_vision",
    }
