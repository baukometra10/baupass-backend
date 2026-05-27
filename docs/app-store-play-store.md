# App Store & Play Store (Pilot → Production)

## Android (Play Store)

1. Build signed AAB in CI: `.github/workflows/flutter-worker-apk.yml`
2. Host APK for pilots: `BAUPASS_WORKER_APK_URL` (GitHub Releases or CDN)
3. Play Console: package `com.baupass.worker`, privacy policy URL, data safety form
4. Internal testing track → closed → production

## iOS (TestFlight → App Store)

1. Workflow: `.github/workflows/flutter-worker-ios.yml`
2. `BAUPASS_TESTFLIGHT_URL` in Railway for join page
3. App Store Connect: NFC usage description, location (site attendance)

## Join flow

`join.html` reads `worker-join-config.json` — ensure APK/TestFlight URLs are set.

## Checklist before public listing

- [ ] Privacy policy (GDPR)
- [ ] Support email
- [ ] Screenshots (DE/EN)
- [ ] Enterprise demo on `enterprise` plan
