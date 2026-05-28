# Mitarbeiter-App — Feldtest-Pipeline (DE)

Ablauf: **Git Push → CI baut APK → Install auf Testgerät → NFC/Attendance testen → später Firebase Push**

---

## 1) Git Push

```powershell
cd C:\Users\u4363\Desktop\baustelle
git add .
git commit -m "feat(mobile): worker app update"
.\deploy\github-push.ps1
```

Branch **`main`** triggert automatisch:
- `.github/workflows/flutter-worker-apk.yml` — **Build worker APK**
- `.github/workflows/railway-deploy.yml` — Backend (Railway)

---

## 2) CI — APK automatisch

1. GitHub → **Actions** → **Build worker APK**
2. Warten bis grün (~5–8 Min.)
3. Run öffnen → **Artifacts** → **`baupass-worker-apk`** → `app-release.apk` herunterladen

Manuell starten (andere API-URL):

- Actions → **Build worker APK** → **Run workflow** → `api_base_url` anpassen

Die APK enthält die Backend-URL als `--dart-define=BAUPASS_API_URL=…` (Standard: Railway-Produktion).

Optional dauerhafter Download-Link:

- APK als **GitHub Release** anhängen
- Railway: `BAUPASS_WORKER_APK_URL=https://github.com/…/releases/download/…/app-release.apk`

---

## 3) Install auf Testgerät (Android)

### Voraussetzungen

- Android-Handy mit **NFC** (in Einstellungen aktiv)
- USB-Debugging oder APK per Link/QR sideload
- [Platform Tools (adb)](https://developer.android.com/tools/releases/platform-tools) installiert

### Per USB (empfohlen)

```powershell
.\deploy\install-worker-apk.ps1 -ApkPath "$env:USERPROFILE\Downloads\app-release.apk"
```

Oder manuell:

```powershell
adb devices
adb install -r .\app-release.apk
```

### Per Download-Link

1. APK auf Server legen oder GitHub Release
2. `BAUPASS_WORKER_APK_URL` in Railway setzen
3. Mitarbeiter: `join.html` / Admin-QR **App installieren**

---

## 4) Vorbereitung Admin (~3 Min.)

Ersetze `{BASE}` durch deine Railway-URL, z. B. `https://baupass-production.up.railway.app`.

| Check | URL / Aktion |
|-------|----------------|
| Backend live | `{BASE}/api/health/live` → `alive` |
| Admin v2 | `{BASE}/admin-v2/index.html` |
| Mitarbeiter anlegen | Tab **Mitarbeiter** → Badge-ID + PIN |
| NFC-Karte zuweisen | **NFC-UID** speichern (Spalte `physical_card_id`) |
| App-Zugang | **QR Aktivierung** → Link an Tester |

PowerShell:

```powershell
$BASE = "https://IHR-SERVICE.up.railway.app"
Invoke-RestMethod "$BASE/api/health/live"
```

---

## 5) Test in der App (~5 Min.)

| Schritt | Erwartung |
|---------|-----------|
| App öffnen | Splash → Login |
| **Badge-ID + PIN** | Login OK, Tab **Ausweis** mit Foto/QR |
| Gerät gebunden | Hinweis „Gerät gebunden“ auf Start |
| Tab **Check-in** | NFC-Button sichtbar |
| Karte ans Handy | `Anwesenheit gespeichert: check-in` |
| Erneut scannen | `check-out` oder „Bereits erfasst“ |
| Admin **Anwesenheit** | Eintrag mit Gate „Mitarbeiter-App (NFC)“ |

### Offline-Test (optional)

1. Flugmodus an
2. NFC scannen → „Offline gespeichert“
3. Flugmodus aus → Sync-Icon / automatische Sync-Meldung
4. Admin: Eintrag mit korrektem Zeitstempel

### Typische Fehler

| Meldung | Ursache |
|---------|---------|
| `nfc_card_not_enrolled` | Keine NFC-UID am Mitarbeiter |
| `nfc_uid_mismatch` | Falsche Karte gescannt |
| `worker_geolocation_required` | GPS aus, Firma im Modus `site_app` |
| `device_not_bound` | Altes Gerät / erneut anmelden |
| `outside_geofence` | Nicht am Standort |

---

## 6) Später: Firebase Push

Noch **nicht** in CI — manuell wenn Attendance stabil:

1. Firebase-Projekt + `google-services.json`
2. `firebase_messaging` in `mobile/pubspec.yaml`
3. `PushNotificationService.obtainNativeDeviceToken()` implementieren
4. Profil → Push aktivieren → `POST /api/worker-app/push/register`

Anleitung: `mobile/docs/firebase-push-setup.md`

---

## iPhone (parallel)

- CI: **Build worker iOS** → unsigned `.zip` (TestFlight braucht Apple-Signing lokal)
- Details: `docs/testflight-internal-distribution.md`

---

## Kurz-Checkliste

- [ ] Push auf `main`
- [ ] Actions **Build worker APK** grün
- [ ] APK auf Test-Android installiert
- [ ] Mitarbeiter + NFC-UID im Admin
- [ ] Login + digitale Karte OK
- [ ] NFC Check-in/out im Admin sichtbar
- [ ] (Optional) Offline-Sync OK
- [ ] (Später) Firebase Push
