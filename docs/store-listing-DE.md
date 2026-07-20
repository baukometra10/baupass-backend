# App Store & Google Play — SUPPIX Worker

## Feste Marke (Store)

- **App-Name:** SUPPIX
- **Icon:** `branding/suppix-icon-512.png` (bereits in Flutter/Android/iOS)
- Icon **nicht** pro Firma wechseln — Apple/Google erlauben das nach Veröffentlichung nicht

## White-Label (in der App)

Nach QR-Login:
- Firmenlogo (`brandingLogoData`)
- Akzentfarbe
- Portal-Name

## Google Play

1. Play Console → neue App
2. Package: `com.baupass.worker`
3. Screenshots (mind. 2, besser 4–8):
   - Login mit QR + Rechtliches-Fußzeile
   - Digitaler Ausweis / Home
   - Check-in / Anwesenheit
   - Chat oder Konferenz
   - Profil → Rechtliches
4. Datenschutz-URL: `https://YOUR-DOMAIN/privacy.html`
5. Impressum-URL (optional Support): `https://YOUR-DOMAIN/impressum.html`
6. Data Safety (kurz):
   - Standort: nur während Arbeit am Geofence
   - Fotos/Dateien: Chat-Anhänge, Ausweis
   - Audio: Sprachnotizen / Anrufe
   - Push-Token: FCM
   - Verschlüsselung: Chat E2E wo aktiv
7. Railway: `BAUPASS_PLAY_STORE_URL=`

## Apple App Store

1. App Store Connect → neue App
2. Bundle ID: `com.baupass.worker`
3. Privacy Policy URL: `https://YOUR-DOMAIN/privacy.html`
4. TestFlight zuerst (`BAUPASS_TESTFLIGHT_URL`)
5. Universal Links: `BAUPASS_IOS_TEAM_ID` + AASA auf Server
6. Railway: `BAUPASS_APP_STORE_URL=`
7. App Privacy: Standort, Kontakte nein, Kamera (QR/Video), Mikrofon (Sprachnotiz/Anruf), Fotos (optional)

## Android App Links

Release-Keystore SHA256 in Railway:

```env
BAUPASS_ANDROID_APP_LINK_SHA256=AA:BB:CC:…
```

Prüfen: `https://YOUR-DOMAIN/.well-known/assetlinks.json`

## Build-Befehle

```bash
flutter build appbundle --release --dart-define=BAUPASS_API_URL=https://…
flutter build ipa --release --dart-define=BAUPASS_API_URL=https://…
```
