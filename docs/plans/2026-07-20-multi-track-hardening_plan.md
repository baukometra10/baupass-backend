# Plan: Multi-track Hardening (Cameras · Invoices · Flutter · Ops · Live)

**Datum:** 2026-07-20

## Umgesetzt
- [x] Live-Geräte-Checkliste (`docs/plans/2026-07-20-live-device-checklist.md`)
- [x] RTSP agent: heartbeat nur mit `--heartbeat` (nicht auto bei RTSP)
- [x] Camera bulk: ID-Kollisionen → Suffix; `created`/`updated` getrennt
- [x] Camera Live-UI: healthError / lastSeen / no_snapshot Hinweise
- [x] RQ worker: unused `Connection` Import entfernt
- [x] `/api/health`: 503 nur bei DB-down; degraded = 200
- [x] Enqueue-Failures → dead-letter + job status
- [x] Invoice single retry nur bei `send_failed`
- [x] Invoice print bleibt im sandboxed iframe
- [x] Stripe portal return URL behält Query/Hash
- [x] Flutter GPS leave: 3 Off-Site-Strikes
- [x] Flutter chat: POST mark-read beim Öffnen

## Manuell
- [ ] Gerät: GPS 3× + Chat Unread (Checkliste)
