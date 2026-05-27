# BauPass Worker — Flutter Hybrid App (Enterprise)

**~90%** shared Dart (Android + iOS): login, profile, attendance, tasks shell, API, offline queue.  
**~10%** native NFC only: Kotlin (Android) + Swift (Core NFC) via Platform Channel.

Platform architecture: [docs/enterprise-hybrid-platform-AR.md](../docs/enterprise-hybrid-platform-AR.md)

## Prerequisites

- [Flutter SDK](https://docs.flutter.dev/get-started/install) 3.22+
- Android Studio / Xcode for device builds
- Running BauPass backend (`backend/server.py` or production URL)

## First-time setup

From repo root, generate Flutter platform scaffolding (Gradle, Xcode project files):

```bash
cd mobile
flutter create . --org com.baupass --project-name baupass_worker
flutter pub get
```

Native NFC plugins are already wired:

- `android/app/src/main/kotlin/com/baupass/worker/NfcReaderPlugin.kt`
- `ios/Runner/NfcReaderPlugin.swift`

After `flutter create`, re-apply plugin registration if `MainActivity.kt` or `AppDelegate.swift` were overwritten — copy from this repo or merge manually.

### iOS NFC entitlement

In Xcode → Signing & Capabilities → add **Near Field Communication Tag Reading** and ensure `NFCReaderUsageDescription` is set (see `ios/Runner/Info.plist`).

## Run

```bash
# Android emulator → host machine backend
flutter run --dart-define=BAUPASS_API_URL=http://10.0.2.2:5000

# Physical device → your LAN IP
flutter run --dart-define=BAUPASS_API_URL=https://your-api.example.com
```

## Project layout

```
lib/
  core/           # API client, config, auth (Badge+PIN, access token)
  services/       # NFC channel, attendance, offline queue, cache
  features/
    auth/         # Badge-ID + PIN + access link
    shell/        # Bottom navigation (Home / Attendance / Tasks / Profile)
    home/         # Dashboard
    attendance/   # NFC → Backend (or offline queue)
    profile/      # /api/worker-app/me
    tasks/        # Leave requests + my documents (shared API)
android/          # Kotlin NFC reader (NfcReaderPlugin)
ios/              # Swift Core NFC (NfcReaderPlugin)
```

## Push notifications (FCM / APNs)

1. Create a Firebase project and add `google-services.json` / `GoogleService-Info.plist`.
2. Add `firebase_messaging` to `pubspec.yaml` and implement `PushNotificationService.obtainNativeDeviceToken()`.
3. User enables notifications in **Profile** → registers `deviceToken` at `POST /api/device/register`.

## API

See [docs/worker-mobile-nfc-api.md](../docs/worker-mobile-nfc-api.md).

## Admin v2 (web)

Enterprise admin dashboard: [admin-v2/index.html](../admin-v2/index.html) — uses `/api/v2/admin/overview`, `/api/v2/workers`, `/api/v2/access/live`.

## Related repo components

| Component | Path |
|-----------|------|
| Backend endpoint | `POST /api/worker-app/attendance/nfc` in `backend/server.py` |
| Route registration | `backend/app/api/worker_app_routes.py` |
| Legacy PWA | `emp-app.html`, `worker-app.js` |
| Android HCE (gate emulation) | `android-hce-companion/` (separate from this reader app) |
