# Firebase Push (FCM / APNs) for WorkPass Hybrid Worker App

## 1. Firebase project

1. Create a project at [Firebase Console](https://console.firebase.google.com/).
2. Add **Android** app `com.baupass.worker` → download `google-services.json` → replace `mobile/android/app/google-services.json` (placeholder is CI-only).
3. Add **iOS** app `com.baupass.worker` → download `GoogleService-Info.plist` → replace `mobile/ios/Runner/GoogleService-Info.plist` (placeholder is CI-only).
4. Set on Railway either:
   - `FCM_SERVER_KEY` (legacy), or
   - `FCM_PROJECT_ID` + `FCM_SERVICE_ACCOUNT_JSON` (HTTP v1, preferred for new Firebase projects).
   - `FCM_V1_ONLY=1` — disable legacy `FCM_SERVER_KEY` fallback after v1 is configured.

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
- `lib/services/push_notification_service.dart` — FCM token on login (device binding) + Profile toggle
- `lib/services/push_navigation.dart` — tap opens `baupass://app/...` tabs

For local dev without Firebase files: `flutter run --dart-define=BAUPASS_FCM_TOKEN=test-token`

## 4. Backend registration (hybrid)

On login, the Flutter app sends `device.pushToken` in `POST /api/worker-app/login` (stored on `worker_bound_devices`).

Optional refresh: `POST /api/worker-app/push/register` with `{ pushToken, platform }`.

Status: `GET /api/worker-app/push/status` → `fcmConfigured`, `workerAppKind: hybrid_native`.

## 5. CI APK for join.html

GitHub Actions workflow `Build worker APK` uploads `baupass-worker-apk`. Host the APK and set `BAUPASS_WORKER_APK_URL` on Railway so `join.html` offers the hybrid app download.

## 6. Legacy Web push (deprecated)

Old browser PWA used VAPID (`push_subscriptions`). Production workers should use the **Flutter hybrid app**; Web Push is only a fallback when no FCM token exists.
