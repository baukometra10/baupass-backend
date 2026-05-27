# Firebase Push (FCM / APNs) for BauPass Worker

## 1. Firebase project

1. Create a project at [Firebase Console](https://console.firebase.google.com/).
2. Add **Android** app `com.baupass.worker` → download `google-services.json` → `mobile/android/app/`.
3. Add **iOS** app → download `GoogleService-Info.plist` → `mobile/ios/Runner/`.

## 2. Flutter dependencies

In `mobile/pubspec.yaml` uncomment or add:

```yaml
dependencies:
  firebase_core: ^3.6.0
  firebase_messaging: ^15.1.0
```

Run `flutter pub get`.

## 3. Implement token in `push_notification_service.dart`

```dart
import 'package:firebase_messaging/firebase_messaging.dart';

Future<String?> obtainNativeDeviceToken() async {
  await FirebaseMessaging.instance.requestPermission();
  return FirebaseMessaging.instance.getToken();
}
```

Call `Firebase.initializeApp()` in `main.dart` before `runApp`.

## 4. Backend registration

When the user enables notifications in **Profile**, the app calls:

`POST /api/device/register` with `{ deviceToken, deviceType, deviceName, publicKey }`.

## 5. Web push (PWA)

Worker PWA continues to use VAPID via `/api/worker-app/push-vapid-key` and `/api/worker-app/push-subscribe` — separate from native FCM.
