# Android — morgen Play Store (Kurzplan)

Ziel: Worker-App als echte App in Google Play (Internal Testing zuerst).  
iPhone/TestFlight bleibt pausiert, bis Firmen-Team-Zugang da ist.

## Heute / morgen — Reihenfolge

1. **Play Console** (Firmen-Account, ~25 \$ einmalig falls neu)
   - App anlegen oder vorhandene öffnen
   - Package: `com.baupass.worker`
2. **Build holen**
   - GitHub → Actions → **Build worker APK** → Artifact `baupass-worker-apk`
   - Oder lokal: `cd mobile && flutter build appbundle --release`
3. **Internal testing track**
   - AAB hochladen (Play will **AAB**, nicht nur APK)
   - Tester-E-Mails hinzufügen
4. **Listing Minimum**
   - Kurzbeschreibung, 2–4 Screenshots, Datenschutz-URL, Data Safety
5. **Railway**
   ```env
   BAUPASS_PLAY_STORE_URL=https://play.google.com/store/apps/details?id=com.baupass.worker
   ```
   (oder Internal-Testing-Link, solange nicht public)

## Wichtig

| APK (jetzt) | AAB (Play) |
|-------------|------------|
| Gut für Direkt-Download / Pilot | Pflicht für Play Store Upload |
| CI: `flutter-worker-apk.yml` | `flutter build appbundle --release` + Release-Keystore |

Release-Signing (Keystore) muss einmal eingerichtet werden — ohne Firmen-Keystore nur Debug/Upload-Key von Play möglich (Play App Signing).

## Siehe auch

- [app-store-play-store.md](./app-store-play-store.md)
- [store-listing-DE.md](./store-listing-DE.md)
