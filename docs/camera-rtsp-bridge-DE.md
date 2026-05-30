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
  "ppe": false,
  "zone": "Zone A",
  "in_restricted_zone": true,
  "confidence": 0.92
}
```

`worker_id` + vorhandenes Foto → `face_match` wird gesetzt (Stub bis Azure Face / lokales Modell).

## Railway

- `BAUPASS_RTSP_BRIDGE_TOKEN` — geheimer Token für den lokalen RTSP-Agent

## UI

Control Pass → **Geräte** → Panel «Kamera-KI & RTSP-Bridge»
