# Plan: Fast-follow Hardening (K1–K4)

**Datum:** 2026-07-20  
**Kontext:** Nach Anwesenheit UX J1–J7 — User: „setze alles um“ (Smoke, Berlin-today Duplikate, Offline/Push, Admin-v2 Live).

## Phasen

### K1 — Berlin `access_today_prefix` in server.py
Access/Anwesenheit-Tagesfilter auf `access_today_prefix()` (Europe/Berlin).

### K2 — Admin-v2 Live
Access-Tab refresht bei Realtime; Foreman „checked in today“ inkl. `app-login`.

### K3 — Offline / Push
- Offline-Event-Queue: nur erfolgreiche/permanente Events droppen
- Chat-Offline: `serverMessageId` vor Attachment-Retry behalten
- Worker-Chat Push: `messageId`/`threadId` in Payload
- SW: kein zweites Browser-Notification; `pushsubscriptionchange`

### K4 — Live-Smoke
Code-Pfad-Checks; manuelle GPS/Chat-Preview bleiben optional (Gerät nötig).

## Status
- [x] K1–K3 umgesetzt
- [x] Pytest Presence/Hours + access_today_prefix
- [ ] Manuell auf Prod: GPS 3× Off-Site, Chat Unread, Invoice Preview
