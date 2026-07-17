# Platform bugfest notes — chat41 / conference sprint

## Fixed / improved in this sprint

- ICE diagnostics: Admin Call overlay **Netz** button → `/api/chat/calls/ice-config`
- Chat search: Admin + Worker merge **server search** with local cache
- Worker call history: Flutter Chat AppBar history sheet (`/calls/history`)
- Conference hangup ends LiveKit room when active
- ice_servers_diagnostics endpoint kept for admin ICE panel

## Known remaining (not blockers for 1:1)

- Flutter conference UI is invite/join-token sheet; full LiveKit video grid still best on Admin/PWA until native LiveKit SDK wired
- LiveKit requires `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` or conference returns 503
- iOS TestFlight signed upload still blocked without Apple team access
- Android AAB workflow skips without `ANDROID_KEYSTORE_*` secrets (APK workflow still works)

## Smoke checklist

1. Admin 1:1 call overlay loads (topbar, meters, hangup)
2. Admin ICE button shows server count
3. Admin conference without LiveKit keys → clear error message
4. With LiveKit keys: create room, invite worker, worker PWA accept
5. Chat search returns server hits for older messages
6. Flutter Anrufverlauf sheet opens
