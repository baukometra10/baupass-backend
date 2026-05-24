# System – Arbeitspakete (der Reihe nach)

## 1. Mitarbeiter-PWA
- Tabs Urlaub / Stunden / Docs mit sichtbarem Inhalt
- Kein Reload-Loop (Service Worker)
- Build **20260524a** live prüfen: `/worker-build.json`

## 2. Branding
- BauPass / ControlPass je nach Firmen-Preset
- Karten-Install-Ansicht (`?view=card`)

## 3. Pakete & Rechte
- Gesperrte Tabs mit Hinweis (nicht leer)
- API-Fehler verständlich (`formatWorkerApiError`)

## 4. Admin & Links
- `PUBLIC_BASE_URL` auf Railway = aktuelle Domain
- Mitarbeiter-Links nutzen Build aus `worker-build.json`
- Alte API-Host-Einträge im Browser: Site-Daten löschen oder neuen Link

## 5. Stabilität / Deploy
- Docker: `baupass/baupass:latest` → Service **web-production-922fe**
- Optional Railway: `BAUPASS_ENABLE_IMAP_POLLER=0` für schnelleren Start

## Deploy (ohne GitHub)

```powershell
cd C:\Users\u4363\Desktop\baustelle
docker build -t baupass/baupass:latest .
docker push baupass/baupass:latest
```

Railway → Redeploy.
