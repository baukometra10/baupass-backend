# Chat follow-up tracks

Status after admin Phase 1/2 (`chat36`/`chat37`) and multi-track sprint (`chat38` + Flutter `0.1.11+32`).

## Done in this sprint

- Admin push status bar + activate/deactivate (`GET /api/chat/push-status`, `POST /api/chat/push-unsubscribe`)
- Server-backed thread pin/mute (`GET/PUT /api/chat/thread-prefs`) with localStorage fallback
- Flutter reply quotes, long-press menu (reply/copy/delete), in-conversation search
- TestFlight docs: signing secret matrix + build `0.1.11+32`

## Still open

### WebRTC / calls E2E
Backend unit coverage lives in `backend/tests/test_voice_calls.py`.
Browser smoke is still missing. Preferred next step:

- Add `tests/e2e/chat-calls.spec.js`
- Mock `navigator.mediaDevices.getUserMedia` and `RTCPeerConnection`
- Assert admin dial UI opens and worker accept/end overlays render without real media

### View-once voice (native hard enforce)
Soft flags exist on upload; Flutter/admin still need strict one-play + revoke semantics end-to-end.

### Signed TestFlight CI
Unsigned iOS zip already builds. Remaining work is wiring ASC API/cert secrets into a dedicated workflow and uploading IPA.

### Message-level server pins
Thread prefs are server-backed now. Per-message pin/star prefs remain client-local in `chat-message-prefs.js`.
