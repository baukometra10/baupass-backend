# WorkPass Mitarbeiter-App — Verteilung (APK + TestFlight)

Schnelle Feldtests ohne Google Play oder App Store.

## Pipeline (empfohlen)

```
Git Push (main) → GitHub Actions „Build worker APK“ → Artifact download → adb install → NFC testen
```

Ausführliche Checkliste: **[mobile-field-test-DE.md](./mobile-field-test-DE.md)**

Windows-Install:

```powershell
.\deploy\install-worker-apk.ps1 -ApkPath "$env:USERPROFILE\Downloads\app-release.apk"
# oder mit GitHub CLI:
.\deploy\install-worker-apk.ps1 -DownloadLatest
```

## Voraussetzungen

- Flutter SDK 3.22+ (`flutter doctor`)
- Einmalig: `cd mobile && flutter create . --org com.baupass --project-name baupass_worker`
- Backend läuft auf Railway/Render mit `PUBLIC_BASE_URL` gesetzt

## Android — APK sideload

```bash
cd mobile
flutter pub get
flutter build apk --release \
  --dart-define=BAUPASS_API_URL=https://IHR-SERVICE.up.railway.app
```

APK: `mobile/build/app/outputs/flutter-apk/app-release.apk`

1. APK auf internen Fileserver oder GitHub Release hochladen
2. Railway-Variable setzen: `BAUPASS_WORKER_APK_URL=https://…/app-release.apk`
3. Mitarbeiter öffnen `join.html` oder Admin-QR → APK installieren (Unbekannte Quellen erlauben)

## iPhone — TestFlight (Internal)

1. Apple Developer Account + App in App Store Connect anlegen
2. Xcode: Signing Team, NFC Entitlement (`Runner.entitlements`)
3. `flutter build ipa --release --dart-define=BAUPASS_API_URL=https://…`
4. Upload via Transporter oder Xcode → TestFlight → Internal Testing
5. Railway: `BAUPASS_TESTFLIGHT_URL=https://testflight.apple.com/join/XXXXX`

Details: `docs/testflight-internal-distribution.md`

## Backend-Umgebungsvariablen (neu)

| Variable | Default | Bedeutung |
|----------|---------|-----------|
| `BAUPASS_WORKER_DEVICE_BINDING` | `1` | Nur gebundene Geräte dürfen Check-ins senden |
| `BAUPASS_WORKER_JWT` | `1` | Login liefert zusätzlich signiertes JWT |
| `BAUPASS_WORKER_JWT_SECRET` | (Fallback DQR/Identity Secret) | HS256 Secret für Worker-JWT |

PWA (`emp-app.html`) bleibt ohne Device-Binding nutzbar, solange kein `device`-Objekt beim Login mitgeschickt wird.

## API für die Flutter-App

- Login: `POST /api/worker-app/login` mit `device.fingerprint`
- Session: Bearer = `jwt` (bevorzugt) oder `token`, Header `X-Device-Id`
- NFC: `POST /api/worker-app/attendance/nfc`
- Offline: `POST /api/worker-app/offline-events`
- Push: `POST /api/worker-app/push/register`

Vollständiger Vertrag: `docs/worker-mobile-nfc-api.md`
