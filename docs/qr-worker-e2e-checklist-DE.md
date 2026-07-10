# QR → Worker-App → Check-in (E2E)

## Vorbereitung

- [ ] `BAUPASS_WORKER_JWT_SECRET` gesetzt (32+ Zeichen)
- [ ] `BAUPASS_WORKER_DEVICE_BINDING=1`
- [ ] APK oder TestFlight-URL in Railway
- [ ] Mitarbeiter mit Badge + PIN im Admin angelegt

## Android

1. [ ] Admin: Mitarbeiter → **App-Zugang** → QR erzeugen (Link zeigt auf `join.html`)
2. [ ] QR mit **SUPPIX-App** scannen (Kamera-Viewfinder beim ersten Start)
3. [ ] Firmen-Logo/Farben erscheinen nach Scan
4. [ ] Login erfolgreich, `deviceId` gebunden (`platform: android`)
5. [ ] Digitaler Ausweis sichtbar
6. [ ] Manueller GPS Check-in / NFC (falls Gate vorhanden)
7. [ ] Stundennachweis zeigt korrekte Minuten

## iPhone

1. [ ] Gleicher QR-Flow über TestFlight/App Store
2. [ ] `platform: ios` in gebundenen Geräten
3. [ ] Push-Token optional (FCM/APNs konfiguriert)

## PWA Fallback (Notfall)

1. [ ] `join.html` → „Browser-PWA (Fallback)“
2. [ ] Banner „SUPPIX Browser-Fallback“ sichtbar
3. [ ] QR-Scanner auf Login-Seite (Chrome mit BarcodeDetector)
4. [ ] `platform: android` oder `ios`, `channel: pwa_fallback`

## Fehlerbilder

| Symptom | Prüfen |
|---------|--------|
| QR öffnet nur Browser | Deep Link / App installiert? |
| Token ungültig | Einmal-Link schon verwendet? |
| Kein Firmen-Logo | `join-preview` / `/me` company branding |
| 0 Stunden nach Checkout | Fix `attendanceOpen` / manueller Check-in |
