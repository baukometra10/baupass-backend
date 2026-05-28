# Worker Mobile App — NFC Attendance API

Contract between the Flutter employee app and the BauPass backend.

## Authentication

Worker sessions come from `POST /api/worker-app/login`. The Flutter app sends a stable device fingerprint on login; the server binds the session to that device when `BAUPASS_WORKER_DEVICE_BINDING=1` (default).

```http
Authorization: Bearer <jwt_or_opaque_session_token>
X-Device-Id: wbd-…
```

- **Opaque token** (`token` in login response) — backward compatible with PWA.
- **JWT** (`jwt` in login response, HS256) — preferred by Flutter; contains `sub`, `did`, `sid`, `exp`.

### Login (mobile)

```http
POST /api/worker-app/login
Content-Type: application/json

{
  "badgeId": "BP-12345",
  "badgePin": "1234",
  "location": { "latitude": 52.52, "longitude": 13.405 },
  "device": {
    "fingerprint": "uuid-per-install",
    "name": "Pixel 8",
    "platform": "android",
    "pushToken": "optional-fcm-token"
  }
}
```

Response adds `deviceId`, `jwt`, `deviceBindingRequired`.

### Push register (native)

```http
POST /api/worker-app/push/register
Authorization: Bearer <token>
X-Device-Id: wbd-…

{ "pushToken": "…", "platform": "ios" }
```

## Record NFC attendance

```http
POST /api/worker-app/attendance/nfc
Content-Type: application/json
Authorization: Bearer <session_token>
```

### Request body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `nfcUid` | string | yes | Tag UID from native NFC (hex; colons optional) |
| `direction` | string | no | `auto` (default), `check-in`, `check-out`, `toggle` |
| `location` | object | conditional | `{ latitude, longitude }` — required when company `accessMode` is `site_app` |
| `gate` | string | no | Label stored on access log (default: `Mitarbeiter-App (NFC)`) |
| `note` | string | no | Extra note on access log |

### Success `200`

```json
{
  "ok": true,
  "duplicate": false,
  "logId": "log-abc123",
  "direction": "check-in",
  "timestamp": "2026-05-27T08:15:00.000Z",
  "openCheckInToday": true,
  "gate": "Mitarbeiter-App (NFC)"
}
```

When the same direction was recorded within 45 seconds, `duplicate` is `true` and no new row is created.

### Errors

| HTTP | `error` | Meaning |
|------|---------|---------|
| 400 | `missing_nfc_uid` | No UID in body |
| 400 | `invalid_direction` | Unknown direction value |
| 400 | `worker_geolocation_required` | Site app mode requires GPS |
| 401 | `invalid_worker_session` | Missing or expired session |
| 403 | `nfc_card_not_enrolled` | Worker has no `physical_card_id` |
| 403 | `nfc_uid_mismatch` | Scanned UID ≠ enrolled card |
| 403 | `outside_geofence` | Worker outside site radius |
| 403 | `worker_not_active` | Worker status not active |
| 403 | `nfc_badges` (feature) | Plan does not include NFC |
| 403 | `device_not_bound` | `X-Device-Id` does not match session binding |
| 403 | `missing_device_id` | Bound session but no device header |

## Platform channel (Flutter ↔ Native)

Channel name: `com.baupass.worker/nfc`

| Method | Args | Returns |
|--------|------|---------|
| `isAvailable` | — | `bool` |
| `scanTag` | `{ timeoutMs?: number }` | `{ uid: string, platform: "android" \| "ios" }` |

Native implementations:

- Android: `mobile/android/.../NfcReaderPlugin.kt` (Reader Mode)
- iOS: `mobile/ios/Runner/NfcReaderPlugin.swift` (Core NFC)

## Assign NFC card (admin v2)

```http
PATCH /api/v2/workers/{workerId}/physical-card?company_id={cid}
Authorization: Bearer <admin_token>
Content-Type: application/json

{ "physicalCardId": "04A1B2C3D4E5F6" }
```

UI: [admin-v2/index.html](../admin-v2/index.html) → tab **الموظفون**.

## Admin setup

1. Assign `physicalCardId` on the worker (NFC UID from reader or enrollment tool).
2. Ensure company plan includes `nfc_badges` (starter+).
3. Issue worker app access link → employee logs in → taps **Attendance**.

## Attendance flow

```
Employee app → scanTag() → POST /attendance/nfc → access_logs row → JSON success
```

## Offline queue (phone has no internet)

1. App scans NFC locally and enqueues `nfc_attendance` on device.
2. When online, app calls `POST /api/worker-app/offline-events` with the queue.
3. Server replays into `access_logs` using `occurredAt` and `clientEventId` (idempotent).

### Offline event shape

```json
{
  "type": "nfc_attendance",
  "clientEventId": "nfc-1730000000-42",
  "nfcUid": "04A1B2C3D4E5F6",
  "direction": "check-in",
  "occurredAt": "2026-05-27T07:15:00.000Z"
}
```

### Sync response

```json
{
  "ok": true,
  "stored": 1,
  "results": [
    { "ok": true, "type": "nfc_attendance", "logId": "log-…", "direction": "check-in" }
  ]
}
```

## Fallback without phone internet

Use the **physical card on the gate reader** (`POST /api/scan` / `/api/gates/tap`). The reader needs cloud connectivity, not the phone.

See [worker-attendance-fallback-AR.md](./worker-attendance-fallback-AR.md).
