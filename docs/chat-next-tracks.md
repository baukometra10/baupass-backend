# Chat follow-up tracks

Status after sprint `chat39` + Flutter `0.1.12+33` (admin call UI, view-once hard enforce, message pins, WebRTC E2E, TestFlight CI).

## Done

- Admin push status bar + activate/deactivate (`GET /api/chat/push-status`, `POST /api/chat/push-unsubscribe`)
- Server-backed thread pin/mute (`GET/PUT /api/chat/thread-prefs`) with localStorage fallback
- Server-backed per-message pin/star (`GET/PUT /api/chat/message-prefs`) with local fallback + admin hydrate on thread open
- Flutter reply quotes, long-press menu (reply/copy/delete), in-conversation search
- Admin Anrufbildschirm: WA-style round controls, ring elapsed timer, connecting/unreachable states, missed outbound → „Nicht erreicht“
- View-once voice: consume table + download 410; admin/worker `consumeFn`; Flutter clear-cache + block replay
- WebRTC browser smoke: `tests/e2e/chat-calls.spec.js` (mocked getUserMedia/RTCPeerConnection + chat APIs)
- Signed TestFlight workflow: `.github/workflows/ios-testflight.yml` (skips until ASC/signing secrets exist)

## Optional next

- Worker-side message-prefs API sync (admin sync is live; worker still primarily local)
- Physical-device TestFlight QA checklist in `docs/testflight-internal-distribution.md`
