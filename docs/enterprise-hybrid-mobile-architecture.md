# Enterprise Hybrid Mobile Application — Architecture

**Status:** Canonical reference (May 2026)  
**Product:** WorkPass worker (employee) application  
**Decision:** Hybrid native mobile app — **not** a PWA

---

## Why not a PWA?

The employee app requires **real native NFC** on Android and iPhone. Browsers and PWAs cannot reliably read physical NFC tag UIDs on iOS (Apple restricts NFC to native apps and Wallet). WorkPass therefore uses a **Hybrid Enterprise Mobile Application** with a thin native layer per platform.

---

## System components

| Layer | Role | Implementation in repo |
|-------|------|-------------------------|
| **Enterprise Backend API** | Auth, employees, attendance, NFC validation, reporting, devices, audit | `backend/server.py`, `backend/app/domains/`, `/api/worker-app/*` |
| **Admin Dashboard (Web)** | Manage workers, permissions, attendance logs, analytics | `app.js` / `index.html` (full), `admin-v2/` (light v2 API) |
| **Mobile app (Hybrid)** | Employee UI, workflows, API client, offline queue | `mobile/` (Flutter) |
| **Native NFC layer** | Read RFID/NFC tag UID only | Kotlin (Android), Swift (iOS) |

---

## Hybrid split (~90% / ~10%)

### Shared (~90%) — Flutter

Single codebase for Android and iOS:

- UI and navigation
- Business logic and state
- API communication (`mobile/lib/core/api_client.dart`)
- Authentication (Badge-ID + PIN, one-time access token)
- Attendance workflow and offline sync
- Notifications scaffold (`push_notification_service.dart`)

### Native (~10%) — per OS

| Platform | Technology | File |
|----------|------------|------|
| Android | Kotlin, `NfcAdapter` Reader Mode | `mobile/android/app/src/main/kotlin/com/baupass/worker/NfcReaderPlugin.kt` |
| iPhone | Swift, Core NFC | `mobile/ios/Runner/NfcReaderPlugin.swift` |

**Bridge:** Flutter Platform Channel `com.baupass.worker/nfc`

- Methods: `isAvailable`, `scanTag`
- Result: `{ "uid": "<hex>" }`

Registration in `MainActivity.kt` (Android). iOS registers the plugin in the Flutter engine.

---

## Attendance flow (NFC)

1. Employee opens the mobile app and signs in.
2. Employee taps **Attendance** and starts an NFC scan.
3. Native layer opens an NFC session and reads the **tag UID** (no card emulation).
4. Flutter sends the UID securely to the backend, e.g. `POST /api/worker-app/attendance/nfc`.
5. Backend matches `physical_card_id`, applies geofence/debounce rules, writes `access_logs`.

**Offline:** events are queued locally and replayed via `POST /api/worker-app/offline-events` (type `nfc_attendance`). Physical card at a gate reader remains the primary fallback when the phone has no network.

See [worker-mobile-nfc-api.md](./worker-mobile-nfc-api.md) and [worker-attendance-fallback-AR.md](./worker-attendance-fallback-AR.md).

---

## NFC scope and Apple review

The app performs **standard NFC tag reading** only. It does **not** implement:

- Card emulation (HCE)
- Secure Element emulation
- Payment or transit passes

Therefore:

- **Android:** `NFC` permission and Reader Mode in the manifest.
- **iPhone:** Core NFC entitlement and usage description in `Info.plist`; no special “payment NFC” approval beyond normal app review and accurate privacy declarations.

A separate experimental HCE companion exists under `android-hce-companion/` and is **not** part of this worker attendance path.

---

## Deployment strategy (phased)

### Phase 1 — Internal distribution (recommended now)

Prioritize speed, NFC field testing, and rapid updates **without** waiting for public store review.

| Platform | Approach |
|----------|----------|
| **Android** | Direct **APK** (link, email, QR, MDM, or enterprise store). CI: `.github/workflows/flutter-worker-apk.yml` → GitHub Actions artifact. |
| **iPhone** | **TestFlight** for internal testers and controlled rollout. |

Benefits: faster iteration, easier NFC debugging, flexible rollout during stabilization.

### Phase 2 — Public stores (optional, when stable)

When the platform is production-ready, the organization may:

- Publish on **Google Play** and **App Store**, and/or
- Continue **enterprise / internal** distribution (MDM, Apple Business Manager custom apps, private Play tracks)

Choice depends on company policy, scale, and compliance — not a technical blocker in the architecture.

See [distribute-worker-app-AR.md](./distribute-worker-app-AR.md) (Arabic) for APK and CI steps.

### Employee join / QR onboarding

1. Admin creates a one-time link: `POST /api/workers/{id}/app-access`
2. Primary URL: `/join.html?access=...&launch=1` (store/APK/TestFlight buttons from `worker-join-config.json`)
3. Deep link: `baupass://join?access=...` → Flutter auto-login via `app_links`
4. Admin v2: **QR تفعيل** on the workers tab

See [testflight-internal-distribution.md](./testflight-internal-distribution.md).

---

## Relationship to legacy PWA

`emp-app.html`, `worker-install.html`, and `worker-app.js` remain as **legacy / fallback** (QR badge, install-to-home-screen). New employee NFC attendance is implemented in **`mobile/` (Flutter)**. Admin onboarding QR should eventually target the native app join flow, not only PWA install.

---

## Related documents

- [enterprise-hybrid-platform-AR.md](./enterprise-hybrid-platform-AR.md) — Arabic overview + diagram
- [worker-mobile-nfc-api.md](./worker-mobile-nfc-api.md) — API contract
- [field-test-checklist-AR.md](./field-test-checklist-AR.md) — field validation
- [mobile/README.md](../mobile/README.md) — developer setup
