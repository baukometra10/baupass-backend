# Chat follow-up tracks

Status after sprint `chat40` (worker message-prefs sync) on top of `chat39` + Flutter `0.1.12+33`.

## Done

- Admin push status bar + activate/deactivate (`GET /api/chat/push-status`, `POST /api/chat/push-unsubscribe`)
- Server-backed thread pin/mute (`GET/PUT /api/chat/thread-prefs`) with localStorage fallback
- Server-backed per-message pin/star for **admin and worker** (`GET/PUT …/message-prefs`)
- Flutter reply quotes, long-press menu (reply/copy/delete), in-conversation search
- Admin Anrufbildschirm: WA-style round controls, ring elapsed timer, connecting/unreachable states, missed outbound → „Nicht erreicht“
- View-once voice: consume table + download 410; admin/worker `consumeFn`; Flutter clear-cache + block replay
- WebRTC browser smoke: `tests/e2e/chat-calls.spec.js` (mocked getUserMedia/RTCPeerConnection + chat APIs)
- Signed TestFlight workflow: `.github/workflows/ios-testflight.yml` (skips until ASC/signing secrets exist)

## Still operational (not code)

1. Configure GitHub secrets for signed TestFlight (see `docs/testflight-internal-distribution.md`)
2. Build + upload IPA `0.1.12+33` (CI or lokal)
3. Run physical-device QA checklist (Calls / CallKit / Media / Push)

## Optional later

- Flutter pin/star UI parity with worker web
- Live (non-mocked) WebRTC Playwright against staging fixtures
