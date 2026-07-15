# TestFlight & internal distribution (WorkPass Worker)

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

1. **App Store Connect** → My Apps → **+** → New App → iOS, name *WorkPass Worker*.
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
   - **Open in WorkPass app** (`baupass://join?access=...`) if installed
   - **Android APK** / **TestFlight** buttons from config
   - **PWA fallback** if needed
4. After install, scan again or tap **In App öffnen** — Flutter logs in via one-time `accessToken`.

---

## CI: iOS build

- **Unsigned** zip: `.github/workflows/flutter-worker-ios.yml` → artifact `baupass-worker-ios-unsigned`.
- **Signed TestFlight IPA**: `.github/workflows/ios-testflight.yml` (manual or push to `mobile/**`).

### Secrets for signed upload

| Secret | Purpose |
|--------|---------|
| `APP_STORE_CONNECT_API_KEY_ID` | ASC API Key ID |
| `APP_STORE_CONNECT_ISSUER_ID` | ASC Issuer ID |
| `APP_STORE_CONNECT_API_KEY_P8` | Contents of `.p8` key |
| `IOS_DISTRIBUTION_CERT_P12_BASE64` | Base64 of distribution `.p12` |
| `IOS_DISTRIBUTION_CERT_PASSWORD` | `.p12` password |
| `IOS_PROVISIONING_PROFILE_BASE64` | Base64 of App Store provisioning profile |
| `IOS_TEAM_ID` | Optional Apple Team ID for Xcode project |

If any required secret is missing, the TestFlight job **skips** (unsigned workflow still builds).

Until secrets are configured, use local signing:

```bash
cd mobile
flutter pub get
flutter build ipa --release \
  --dart-define=BAUPASS_API_URL=https://baupass-production.up.railway.app
```

Upload `build/ios/ipa/*.ipa` via **Transporter** or Xcode Organizer.

---

## Build matrix (chat / calls)

| Build | Highlights |
|-------|------------|
| **0.1.9+26** | CallKit incoming UI |
| **0.1.10+27** | Gallery, location, WhatsApp voice bar, inline images |
| **0.1.10+29** | Image≠audio fix, missed-call only for worker |
| **0.1.10+30** | Call event wake, voice bubble UX, MIME tests |
| **0.1.10+31** | True inline voice playback (`just_audio`) |
| **0.1.11+32** | Flutter reply / long-press menu / in-thread search |
| **0.1.12+33** | View-once voice hard enforce; admin call screen polish |

Current `mobile/pubspec.yaml` target: **0.1.12+33**.

---

## Internal QA checklist (physical iPhone + Admin web)

Tick before promoting to internal TestFlight:

### Calls

- [ ] Admin → Worker: CallKit / full-screen incoming while locked or backgrounded
- [ ] Accept → two-way audio → hang up both sides
- [ ] Decline once → admin sees declined (not “missed for admin”)
- [ ] Ring ~60s unanswered → worker chat shows **Verpasst**; admin has **no** missed bubble for that outbound miss
- [ ] Worker chat AppBar **call** icon → outbound ring → cancel < 60s

### Chat media

- [ ] Worker records Sprachnachricht → admin hears it
- [ ] Flutter voice bubble: play/pause **in chat** (no system player takeover)
- [ ] Admin sends **photo** → worker sees image preview (never an audio player)
- [ ] Tap image → fullscreen; download works
- [ ] **Medien** gallery: Fotos / Sprache / Dateien; delete removes message
- [ ] Standort share → map bubble opens Maps

### Notifications

- [ ] Admin on dashboard (not chat): worker message → sound + browser notification (permission granted)
- [ ] Worker FCM / CallKit for incoming call while backgrounded

### Build command (Mac)

```bash
cd mobile
flutter pub get
flutter build ipa --release \
  --dart-define=BAUPASS_API_URL=https://baupass-production.up.railway.app
```

Upload `build/ios/ipa/*.ipa` via **Transporter** or Xcode Organizer.

### If CallKit does not appear

- Confirm TestFlight build = `0.1.12+33` (or newer).
- iOS **Settings → WorkPass Worker → Notifications** + Microphone.
- CallKit needs a **new native IPA** (PWA-only deploys are not enough).

---

## Related

- [distribute-worker-app-AR.md](./distribute-worker-app-AR.md)
- [enterprise-hybrid-mobile-architecture.md](./enterprise-hybrid-mobile-architecture.md)
- [field-test-checklist-AR.md](./field-test-checklist-AR.md)
