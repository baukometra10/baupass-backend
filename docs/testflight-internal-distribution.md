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

## CI: iOS build (manual secrets)

Workflow `.github/workflows/flutter-worker-ios.yml` builds an unsigned IPA on macOS runners. For TestFlight upload you still need:

- `APPLE_ID`, `APP_STORE_CONNECT_API_KEY`, or certificate secrets in GitHub

Until secrets are configured, use local `flutter build ipa` + Transporter.

---

## CallKit & voice calls (iOS TestFlight)

Build **0.1.9+26** and later include native incoming-call UI via `flutter_callkit_incoming`.  
Build **0.1.10+27** and later add chat parity: inline images, media gallery, location sharing, WhatsApp-style voice recording bar.  
Build **0.1.10+29** hardens image-vs-audio classification and worker missed-call visibility.  
Build **0.1.10+30** adds **inline Sprachnachricht playback**, faster call wake (event poll + app-resume), and outgoing call from chat.

### What to test on a physical iPhone

1. Install the TestFlight build and log in as a **test worker** with chat enabled.
2. From **Admin v2 → Chat**, start a voice call to that worker.
3. Lock the phone or background the app — expect the **native CallKit** incoming screen (not only an in-app banner).
4. Accept the call, verify two-way audio, then hang up from either side.
5. Decline once and confirm the admin sees **declined** / missed state in chat.
6. From Flutter chat, tap the **call** icon — employer should ring; cancel within 60s.
7. Let an admin call ring out (~60s) — worker chat shows **Verpasst**; admin should **not** see a missed-call bubble for that outbound miss.

### iOS capabilities in this repo

- `Info.plist` → `UIBackgroundModes`: `voip`, `audio`, `remote-notification`
- Microphone usage string for WebRTC voice
- Chat poll interval in the Flutter app: **4s** (faster message sync when realtime is unavailable)

### If CallKit does not appear

- Confirm the build number in TestFlight matches `pubspec.yaml` (`0.1.10+30` or newer for inline voice + call reliability; `0.1.10+27`+ for chat gallery/location/voice bar; `0.1.9+26`+ for CallKit).
- Check iOS **Settings → WorkPass Worker → Notifications** and microphone permission.
- First upload after adding CallKit must be a **new native build** (PWA-only changes are not enough).

---

## Chat features (iOS TestFlight, build 0.1.10+30+)

### What to test

1. **Sprachnachricht** — tap mic → WhatsApp-style bar (timer, waveform, pause, view-once toggle, send). Send to admin; admin should receive playable voice. **In Flutter**, tap the bubble (play icon + waveform); audio opens via the system player with in-bubble progress UX.
2. **Standort** — pin icon in compose → GPS sheet → send. Admin chat shows location bubble; tap opens Maps.
3. **Fotos** — attach image; inline preview in thread; tap for fullscreen. **Medien** icon (AppBar) opens gallery with tabs (Alle/Fotos/Sprache/Dateien). Admin image send must show as **photo**, never as audio player.
4. **View-once voice** — enable “1” toggle before send; recipient can listen once (PWA/admin); native playback is inline (view-once still enforced on web clients).

### Build command (Mac)

```bash
cd mobile
flutter pub get
flutter build ipa --release \
  --dart-define=BAUPASS_API_URL=https://baupass-production.up.railway.app
```

Upload `build/ios/ipa/*.ipa` via **Transporter** or Xcode Organizer.

---

## Related

- [distribute-worker-app-AR.md](./distribute-worker-app-AR.md)
- [enterprise-hybrid-mobile-architecture.md](./enterprise-hybrid-mobile-architecture.md)
- [field-test-checklist-AR.md](./field-test-checklist-AR.md)
