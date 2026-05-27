# TestFlight & internal distribution (BauPass Worker)

## Overview

| Platform | Phase 1 (now) | Configuration |
|----------|-----------------|---------------|
| Android | APK via CI or direct link | `BAUPASS_WORKER_APK_URL` in Railway/env |
| iPhone | TestFlight | `BAUPASS_TESTFLIGHT_URL` in Railway/env |

Employee onboarding uses **`/join.html?access=...`** (QR from Admin v2 or legacy admin).

---

## Railway / production env

Set on the backend service:

```env
PUBLIC_BASE_URL=https://baupass-production.up.railway.app
BAUPASS_WORKER_APK_URL=https://.../app-release.apk
BAUPASS_TESTFLIGHT_URL=https://testflight.apple.com/join/XXXXXXXX
# Optional later:
# BAUPASS_PLAY_STORE_URL=
# BAUPASS_APP_STORE_URL=
```

`join.html` loads `./worker-join-config.json` from these variables.

---

## Android APK (GitHub Actions)

1. Push to `main` (or run workflow **Build worker APK** manually).
2. Download artifact `baupass-worker-apk`.
3. Host the APK (GitHub Release asset, internal file server, or MDM).
4. Set `BAUPASS_WORKER_APK_URL` to the public HTTPS URL.

---

## iPhone — TestFlight setup

### Prerequisites

- Apple Developer Program ($99/year)
- Mac with Xcode (for first upload) or CI with signing secrets
- Bundle ID: `com.baupass.worker` (match Flutter project)

### Steps

1. **App Store Connect** → My Apps → **+** → New App → iOS, name *BauPass Worker*.
2. **Certificates & Profiles** → iOS Distribution certificate + App Store profile for the bundle ID.
3. Enable **NFC Tag Reading** capability (Core NFC) — matches `Info.plist` usage string.
4. Build IPA locally:
   ```bash
   cd mobile
   flutter create . --org com.baupass --project-name baupass_worker
   flutter pub get
   flutter build ipa --release \
     --dart-define=BAUPASS_API_URL=https://baupass-production.up.railway.app
   ```
5. Upload with **Transporter** or Xcode → Organizer → Distribute → App Store Connect.
6. In App Store Connect → **TestFlight** → add internal testers (same team) or external group.
7. Copy the public TestFlight invite link → set `BAUPASS_TESTFLIGHT_URL`.

### Review notes (first build)

- Category: Business
- Explain NFC: “Employees tap physical ID cards to record site attendance.”
- Provide a **demo admin account** and **test worker** with a one-time join link for reviewers.
- Privacy policy URL (required before external TestFlight / App Store).

---

## Join flow (employee)

1. Admin: **Admin v2** → Workers → **QR تفعيل** (or legacy admin **App-Link**).
2. Employee scans QR with the phone camera.
3. Browser opens `join.html`:
   - **Open in BauPass app** (`baupass://join?access=...`) if installed
   - **Android APK** / **TestFlight** buttons from config
   - **PWA fallback** if needed
4. After install, scan again or tap **In App öffnen** — Flutter logs in via one-time `accessToken`.

---

## CI: iOS build (manual secrets)

Workflow `.github/workflows/flutter-worker-ios.yml` builds an unsigned IPA on macOS runners. For TestFlight upload you still need:

- `APPLE_ID`, `APP_STORE_CONNECT_API_KEY`, or certificate secrets in GitHub

Until secrets are configured, use local `flutter build ipa` + Transporter.

---

## Related

- [distribute-worker-app-AR.md](./distribute-worker-app-AR.md)
- [enterprise-hybrid-mobile-architecture.md](./enterprise-hybrid-mobile-architecture.md)
- [field-test-checklist-AR.md](./field-test-checklist-AR.md)
