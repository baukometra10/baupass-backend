# Kamera / RTSP-Bridge

## Endpunkte

| Methode | Pfad | Zweck |
|---------|------|--------|
| POST | `/api/integrations/cameras/bulk` | Mehrere Kameras (JSON `cameras[]` oder `lines` Text) |
| GET | `/api/integrations/cameras/setup` | Bridge-Setup (Company-ID, API-URL, Agent-Hinweise) |
| GET | `/api/integrations/cameras` | Registrierte Kameras + Online-Status |
| POST | `/api/integrations/cameras` | Kamera registrieren |
| PUT | `/api/integrations/cameras/<id>` | Kamera bearbeiten |
| DELETE | `/api/integrations/cameras/<id>` | Kamera löschen |
| GET | `/api/integrations/cameras/<id>/snapshot` | Live-Snapshot (JSON oder `?format=jpeg`) |
| POST | `/api/integrations/cameras/rtsp-ingest` | RTSP-Agent / NVR-Webhook |
| POST | `/api/integrations/security-cameras/events` | Standard-Kamera-Event (Session) |
| GET | `/api/integrations/cameras/events` | Letzte Ereignisse (UI) |

## Authentifizierung (RTSP-Ingest)

1. `X-WorkPass-Rtsp-Token` = `BAUPASS_RTSP_BRIDGE_TOKEN` (+ optional `X-WorkPass-Company-Id`)
2. `X-Device-API-Key` (registriertes Gerät)
3. Admin-Session (Cookie/Bearer)

## Body (JSON)

```json
{
  "companyId": "cmp-abc123",
  "camera_id": "cam-gate-north",
  "camera_name": "Tor Nord",
  "location": "Baustelle A",
  "event_type": "motion",
  "heartbeat": false,
  "worker_id": "w-xyz",
  "image_base64": "<JPEG base64 optional>",
  "clip_base64": "<MP4 base64 optional, 5–10s evidence>",
  "ppe": false,
  "zone": "Zone A",
  "in_restricted_zone": true,
  "confidence": 0.92
}
```

**Heartbeat only** (kein Ereignis, nur Online-Status + Snapshot):

```json
{
  "companyId": "cmp-abc123",
  "camera_id": "cam-gate-north",
  "heartbeat": true,
  "image_base64": "<optional>"
}
```

## Automatische Benachrichtigungen

Bei Verstößen (PSA, Sperrzone, unbekannte Person, …):

- Sicherheits-Alert in der Datenbank
- Admin-Posteingang (Inbox)
- E-Mail mit PDF-Anhang an Firmen-Admins

**Offline-Erkennung:** Hintergrund-Job prüft alle ~120 s (`BAUPASS_CAMERA_HEALTH_SECONDS`).  
Kein Heartbeat innerhalb von 180 s (`BAUPASS_CAMERA_ONLINE_THRESHOLD_SECONDS`) → E-Mail + Alert.

**Nachtbericht:** Täglicher Job (`BAUPASS_CAMERA_NIGHTLY_DIGEST=1`) — PDF mit Vorfällen der letzten 12 h.

## Kamera-Nachtschicht (Watch-Mode)

Außerhalb der Betriebszeiten (Standard 06:00–18:00, Mo–Fr, TZ `Europe/Berlin`):

- Events werden höher priorisiert (`afterHours`), Bewegung → „Verdächtiger Vorfall“ (kein bestätigter Diebstahl)
- Kritische Events erzwingen Snapshot (Payload oder letzter Heartbeat-Frame)
- Critical-Pack mit **Polizei-Vorschlag** (Land/Stadt/Koordinaten, OSM-Cache) — **kein Auto-Notruf**
- Critical: SMS/Push an Firma + optional kurzer Video-Clip (5–10 s) vom RTSP-Agent
- Fehlalarm-Feedback senkt Wiederholungsalarme (Lern-Schwellen)
- Multi-Standort: Watch-Zeiten/Koordinaten pro Site (`camera_watch_sites`, Location = Site-Key)
- UI: `/admin-v2/camera-watch.html` (Einstellungen, Sites, Eskalations-Detail)
- API:
  - `GET/PUT /api/integrations/cameras/watch`
  - `PUT/DELETE /api/integrations/cameras/watch/sites/<site_key>`
  - `GET /api/integrations/cameras/escalations[/<id>]`
  - `POST .../escalations/<id>/ack`
  - `POST .../escalations/<id>/false-positive`

**Vision-Job** (alle ~300 s, `BAUPASS_CAMERA_VISION_SECONDS`): holt Snapshots nach Feierabend und analysiert (OpenAI/Azure Vision oder Heuristik).

| Env | Zweck |
|-----|--------|
| `BAUPASS_CAMERA_VISION_JOB` | Job an/aus (default an) |
| `BAUPASS_CAMERA_VISION_HEURISTIC` | Heuristik ohne Cloud-Key (default an) |
| `OPENAI_API_KEY` / Azure Vision Vars | echte Frame-Analyse |
| `BAUPASS_CAMERA_VISION_DEDUP_MINUTES` | Dedup pro Kamera (default 10) |
| `BAUPASS_POLICE_OSM` | OSM/Overpass für Polizei-Stationen (default an) |
| `BAUPASS_OVERPASS_URL` | optionaler Overpass-Endpoint |
| `BAUPASS_CAMERA_CLIP` | Agent: immer Clip mitschicken |
| `BAUPASS_CAMERA_CLIP_SECONDS` | Clip-Länge 5–10 (default 8) |

## Gesichtserkennung

Mit `worker_id` + Worker-Foto → Stub `face_match`. Mit `image_base64` + Azure:

- `BAUPASS_AZURE_FACE_ENDPOINT`
- `BAUPASS_AZURE_FACE_KEY`
- optional `BAUPASS_AZURE_FACE_MIN_CONFIDENCE` (Standard `0.5`)

## Massen-Import (UI)

WorkPass → **Geräte** → Tab **Massen-Import**

```
Tor Nord; Eingang; rtsp://192.168.1.101/stream1
Halle Ost; Lager; rtsp://192.168.1.102/stream1
```

API:

```json
POST /api/integrations/cameras/bulk
{ "lines": "Tor Nord; Eingang; rtsp://...\nHalle; Lager; rtsp://..." }
```

## Multi-Kamera-Agent

```bash
python scripts/rtsp_camera_agent.py --cameras-file cameras.json --snapshot --interval 120
```

`cameras.json` (aus UI Tab «Bridge einrichten» herunterladen):

```json
{
  "apiUrl": "https://…",
  "companyId": "cmp-…",
  "cameras": [
    {"id": "cam-tor-nord", "name": "Tor Nord", "location": "Eingang", "rtsp_url": "rtsp://…"}
  ]
}
```

## Demo-Agent (Einzelkamera)

```bash
set BAUPASS_API_URL=https://baupass-production.up.railway.app
set BAUPASS_RTSP_BRIDGE_TOKEN=…
set BAUPASS_COMPANY_ID=cmp-…
set BAUPASS_CAMERA_RTSP_URL=rtsp://192.168.1.50/stream1
python scripts/rtsp_camera_agent.py --interval 60 --snapshot
```

Kritischer Event mit Evidence-Clip:

```bash
python scripts/rtsp_camera_agent.py --once --event forced_entry --snapshot --clip --clip-seconds 8
```

Heartbeat:

```bash
python scripts/rtsp_camera_agent.py --once --heartbeat --snapshot
```

## Railway / ENV

| Variable | Standard | Bedeutung |
|----------|----------|-----------|
| `BAUPASS_RTSP_BRIDGE_TOKEN` | — | Geheimer Token für lokalen Agent |
| `BAUPASS_CAMERA_HEALTH_SECONDS` | `120` | Intervall Offline-Prüfung |
| `BAUPASS_CAMERA_ONLINE_THRESHOLD_SECONDS` | `180` | Online wenn Heartbeat jünger |
| `BAUPASS_CAMERA_NIGHTLY_DIGEST` | `1` | Nachtbericht aktiv |
| `BAUPASS_CAMERA_DIGEST_HOURS` | `12` | Zeitraum Nachtbericht |

## UI

WorkPass → **Geräte** → Panel «Kamera-KI & RTSP-Bridge»

- Kameras registrieren
- Online/Offline-Status
- Live-Snapshot (letztes Bild vom Agent)
- Sicherheitsereignisse

WorkPass → **Betrieb** → **Kamera-Wächter** (`/admin-v2/camera-watch.html`)

- Firmen- und Standort-Arbeitszeiten, Quiet-Rules, Zwei-Augen-Ack
- Feiertage / Sonderzeiten (Overrides)
- Eskalations-Kette (Zweitkontakt → Security-Webhook, kein Auto-Notruf)
- Offene Eskalationen mit Snapshot/Clip, Export PDF/ZIP, Ack / Fehlalarm
- Lagekarte (Kameras + offene Escalations)

**Wichtig Superadmin:** Vor Massen-Import / Kamera-Anlage eine Firma in der Vorschau wählen — sonst `company_id_required`.

### NVR-Webhooks

```
POST /api/integrations/cameras/nvr/hikvision
POST /api/integrations/cameras/nvr/dahua
POST /api/integrations/cameras/nvr/generic
```

Auth wie RTSP-Ingest (`X-WorkPass-Rtsp-Token` + `X-WorkPass-Company-Id`).
