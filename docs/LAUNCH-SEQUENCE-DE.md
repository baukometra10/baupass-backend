# SUPPIX Launch-Sequenz (Schritt für Schritt)

Production-URL: `https://suppix-workpass-ai.up.railway.app`

## 1 — Flutter APK / TestFlight

```bash
cd mobile
flutter pub get
flutter build apk --release --dart-define=BAUPASS_API_URL=https://suppix-workpass-ai.up.railway.app
# iOS (Mac): flutter build ipa --release --dart-define=BAUPASS_API_URL=...
```

- GitHub Actions: Workflow **mobile-release** (Push auf `main` mit `mobile/**`)
- APK aus Release → Railway-Variable setzen:

```env
BAUPASS_WORKER_APK_URL=https://…/app-release.apk
BAUPASS_TESTFLIGHT_URL=https://testflight.apple.com/join/…
```

Prüfen: `GET /api/worker-app/mobile-setup` und `GET /worker-join-config.json`

## 2 — RQ Worker Service (Railway)

Zweite Service-Instanz im gleichen Railway-Projekt:

| Setting | Wert |
|---------|------|
| Start Command | `python -m backend.app.tasks.worker` |
| Dockerfile | gleiches Repo |
| Variables | `REDIS_URL`, `BAUPASS_DB_PATH`, Secrets wie API |
| Volume | `/data` (bei SQLite) |

Prüfen: `GET /api/platform/setup-status` → `workerService.checklist.ready`

Details: `deploy/railway-worker.service.md`

## 3 — QR → App → Check-in (E2E)

Checkliste: `docs/qr-worker-e2e-checklist-DE.md`

Kurz: Admin QR → `join.html` → SUPPIX-App → Firmen-Branding → Gerätebindung → Check-in/NFC.

## 4 — App Store / Play Store (optional)

Vorlage: `docs/store-listing-DE.md`

```env
BAUPASS_PLAY_STORE_URL=https://play.google.com/store/apps/details?id=…
BAUPASS_APP_STORE_URL=https://apps.apple.com/app/id…
```

App-Icon ist **SUPPIX** (fest beim Build). In-App: Firmen-Logo nach Login.

## 5 — PWA nur Fallback

- Primär: Flutter (`join.html` → Deep Link)
- Notfall: `emp-app.html` (Banner „Browser-Fallback“)
- Kein neuer Rollout über PWA als Hauptkanal

## 6 — Admin: kein Legacy für Firmen-Admins

- `admin-v2` ist Standard
- Legacy-Dashboard (`index.html`) nur noch für **Superadmin** sichtbar

## 7 — Universal Links (optional)

```env
BAUPASS_ANDROID_APP_LINK_SHA256=AA:BB:…
BAUPASS_IOS_TEAM_ID=XXXXXXXXXX
```

Verifizierung:
- `/.well-known/assetlinks.json`
- `/.well-known/apple-app-site-association`

## 8 — Smoke nach Deploy

```powershell
.\deploy\railway-launch-verify.ps1
```

Oder manuell: Health, Join-Config, Mobile-Setup, Live-Map-Legende, Rechnungs-PDF.
