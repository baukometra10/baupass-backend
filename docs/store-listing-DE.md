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
3. Screenshots: Login (QR), Ausweis, Check-in, Chat
4. Datenschutz-URL: `PUBLIC_BASE_URL`/privacy (falls vorhanden)
5. Railway: `BAUPASS_PLAY_STORE_URL=`

## Apple App Store

1. App Store Connect → neue App
2. Bundle ID: `com.baupass.worker`
3. TestFlight zuerst (`BAUPASS_TESTFLIGHT_URL`)
4. Universal Links: `BAUPASS_IOS_TEAM_ID` + AASA auf Server
5. Railway: `BAUPASS_APP_STORE_URL=`

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
