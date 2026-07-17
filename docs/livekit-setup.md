# LiveKit Cloud — Firmenkonferenz einrichten

Ziel: Admin startet **Konferenz**, Worker PWA (und später Flutter) joinen mit Video/Audio über LiveKit SFU.

1:1-Anrufe bleiben WebRTC und brauchen **kein** LiveKit.

## 1. LiveKit Cloud Projekt

1. Account: [https://cloud.livekit.io](https://cloud.livekit.io)
2. **Create project** (Region EU wenn möglich)
3. Im Projekt → **Settings → Keys**:
   - **WebSocket URL** → z. B. `wss://your-project-xxxxx.livekit.cloud`
   - **API Key** + **API Secret** (einmal anzeigen / kopieren)

Kosten: participant-minutes (Video). Für Smoke-Tests reicht der Free-Tier meist.

## 2. Railway (Production Backend)

Im Railway-Service der API unter **Variables** setzen (empfohlen mit Prefix):

```env
SUPPIX_LIVEKIT_URL=wss://YOUR_PROJECT.livekit.cloud
SUPPIX_LIVEKIT_API_KEY=APIxxxxxxxx
SUPPIX_LIVEKIT_API_SECRET=secretyyyyy
```

Alternativ akzeptiert das Backend auch die Dashboard-Namen ohne Prefix:

```env
LIVEKIT_URL=wss://YOUR_PROJECT.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxx
LIVEKIT_API_SECRET=secretyyyyy
```

Danach Service **redeploy** / neu starten.

Lokal (`.env` neben Backend / Root): dieselben Variablen.

## 3. Smoke-Test (Admin → Worker PWA)

1. Admin-Chat öffnen (`admin-v2/chat.html` oder Admin-Chat im PWA)
2. Mit einem Worker chatten → **Konferenz** starten
3. Worker PWA (eingeloggt, Chat offen): Invite sollte erscheinen → **Beitreten**
4. Beide Seiten: Mikrofon/Kamera erlauben; Video-Gitter sichtbar

Wenn Keys fehlen: API `503 livekit_not_configured`, Admin zeigt Hinweis.

### Schnell-Check API (eingeloggt)

```http
GET /api/chat/conferences/status
```

Erwartung: `{ "ok": true, "configured": true, "livekitAuthOk": true, "livekitUrl": "wss://..." }`

- `livekitAuthOk: false` → Key/Secret passen nicht zum Projekt  
- `livekitAuthOk: true` + Browser **Internal error** → meist VPN/Firewall/WebSocket (nicht die Railway-Keys). Test: [livekit.io/connection-test](https://livekit.io/connection-test), VPN aus, Inkognito.

## 4. Firewall / Browser

- HTTPS-Seite (oder localhost) — sonst blockiert der Browser Kamera/Mikro
- Corporate Proxy: WebSocket `wss://*.livekit.cloud` muss durch

## 5. Was noch nicht fertig ist

| Client | Status |
|--------|--------|
| Admin / Worker PWA | LiveKit JS (`chat-conference.js`) |
| Flutter Worker | Invite + Token; natives Video-UI folgt |
| FCM Push bei Invite | optional später |

## Siehe auch

- [conference-livekit.md](./conference-livekit.md) — Feature-Kurzüberblick
- [platform-bugfest-chat41.md](./platform-bugfest-chat41.md)
- `.env.railway.example` — Variable-Block LiveKit
