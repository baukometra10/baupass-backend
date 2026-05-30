# Kamera / RTSP-Bridge

## Endpunkte

| Methode | Pfad | Zweck |
|---------|------|--------|
| POST | `/api/integrations/cameras/rtsp-ingest` | RTSP-Agent / NVR-Webhook |
| POST | `/api/integrations/security-cameras/events` | Standard-Kamera-Event (Session) |
| GET | `/api/integrations/cameras/events` | Letzte Ereignisse (UI) |

## Authentifizierung (RTSP-Ingest)

1. `X-BauPass-Rtsp-Token` = `BAUPASS_RTSP_BRIDGE_TOKEN` (+ optional `X-BauPass-Company-Id`)
2. `X-Device-API-Key` (registriertes Gerät)
3. Admin-Session (Cookie/Bearer)

## Body (JSON)

```json
{
  "companyId": "cmp-abc123",
  "camera_id": "cam-gate-north",
  "event_type": "motion",
  "worker_id": "w-xyz",
  "image_base64": "<JPEG base64 optional>",
  "ppe": false,
  "zone": "Zone A",
  "in_restricted_zone": true,
  "confidence": 0.92
}
```

**Gesicht:** Mit `worker_id` + Worker-Foto → Stub `face_match`. Mit `image_base64` + Azure:

- `BAUPASS_AZURE_FACE_ENDPOINT` (z. B. `https://….cognitiveservices.azure.com`)
- `BAUPASS_AZURE_FACE_KEY`
- optional `BAUPASS_AZURE_FACE_MIN_CONFIDENCE` (Standard `0.5`)

## Demo-Agent

```bash
set BAUPASS_API_URL=https://baupass-production.up.railway.app
set BAUPASS_RTSP_BRIDGE_TOKEN=…
set BAUPASS_COMPANY_ID=cmp-…
python scripts/rtsp_camera_agent.py --once
```

## Railway

- `BAUPASS_RTSP_BRIDGE_TOKEN` — geheimer Token für den lokalen RTSP-Agent

## UI

Control Pass → **Geräte** → Panel «Kamera-KI & RTSP-Bridge»
