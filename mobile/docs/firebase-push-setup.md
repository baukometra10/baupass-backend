# Firebase Push (FCM / APNs) for BauPass Worker

## 1. Firebase project

1. Create a project at [Firebase Console](https://console.firebase.google.com/).
2. Add **Android** app `com.baupass.worker` → download `google-services.json` → replace `mobile/android/app/google-services.json` (placeholder is CI-only).
3. Add **iOS** app → download `GoogleService-Info.plist` → `mobile/ios/Runner/` (when iOS scaffold is regenerated).
4. Set `FCM_SERVER_KEY` on Railway (backend legacy server key).

## 2. Flutter dependencies

In `mobile/pubspec.yaml` uncomment or add:

```yaml
dependencies:
  firebase_core: ^3.6.0
  firebase_messaging: ^15.1.0
```

Run `flutter pub get`.

## 3. App code (already wired)

- `lib/firebase_bootstrap.dart` — `Firebase.initializeApp()` + token
- `lib/main.dart` — calls bootstrap before `runApp`
- `lib/services/push_notification_service.dart` — registers token on login when push is enabled in Profile

For local dev without Firebase files: `flutter run --dart-define=BAUPASS_FCM_TOKEN=test-token`

## 4. Backend registration

When the user enables notifications in **Profile**, the app calls:

`POST /api/device/register` with `{ deviceToken, deviceType, deviceName, publicKey }`.

## 5. Web push (PWA)

Worker PWA continues to use VAPID via `/api/worker-app/push-vapid-key` and `/api/worker-app/push-subscribe` — separate from native FCM.
