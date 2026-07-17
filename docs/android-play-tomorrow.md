# Android — morgen Play Store (Kurzplan)

Ziel: Worker-App als echte App in Google Play (Internal Testing zuerst).  
iPhone/TestFlight bleibt pausiert, bis Firmen-Team-Zugang da ist.

## Heute / morgen — Reihenfolge

1. **Play Console** (Firmen-Account, ~25 \$ einmalig falls neu)
   - App anlegen oder vorhandene öffnen
   - Package: `com.baupass.worker`
2. **Release-Keystore + GitHub Secrets** (einmalig)
   - Anleitung: [android-play-keystore-secrets.md](./android-play-keystore-secrets.md)
   - Secrets: `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`
3. **AAB bauen**
   - GitHub → Actions → **Build worker Android AAB** → Artifact `baupass-worker-aab`
   - Oder lokal: `cd mobile && flutter build appbundle --release` (mit `mobile/android/key.properties`)
4. **Internal testing track**
   - AAB hochladen (Play will **AAB**, nicht nur APK)
   - Tester-E-Mails hinzufügen
5. **Listing Minimum**
   - Kurzbeschreibung, 2–4 Screenshots, Datenschutz-URL, Data Safety
6. **Railway**
   ```env
   BAUPASS_PLAY_STORE_URL=https://play.google.com/store/apps/details?id=com.baupass.worker
   ```
   (oder Internal-Testing-Link, solange nicht public)

## Wichtig

| APK (jetzt) | AAB (Play) |
|-------------|------------|
| Gut für Direkt-Download / Pilot | Pflicht für Play Store Upload |
| CI: `flutter-worker-apk.yml` | CI: `flutter-worker-aab.yml` + Release-Keystore |

Ohne Firmen-Keystore nur Debug-Signing lokal — Play-Upload braucht den Upload-Key (siehe Secrets-Doku).

## Siehe auch

- [android-play-keystore-secrets.md](./android-play-keystore-secrets.md)
- [app-store-play-store.md](./app-store-play-store.md)
- [store-listing-DE.md](./store-listing-DE.md)
