# Mobile Voice / Video Call — QA Checklist

Manual device checks after one-way video + PiP/conference polish.

**Devices:** Android 13+ · iOS 16+ · at least one low-end phone.

## Automated (CI / unit) — verified 2026-07-28
- [x] Push `voice-call-missed` → Chat route (not ring UI)
- [x] Deeplink `chat?missed=1&callback=1` → auto callback flag
- [x] Push `morning-brief` → Home tab
- [x] Cold-start pending keys (missed / callback / morning) one-shot
- [x] Backend deeplinks for missed + morning-brief
- [x] Ops loop smoke: Brief → Inbox → Live-Map → Copilot (`autoDial: false`)
- [x] Soft-hints / digest never set auto-dial / auto-approve

## 1:1 Call (device)
- [ ] Outgoing audio connects (no auto-dial elsewhere)
- [ ] Local camera on → peer sees video
- [ ] Peer enables camera late → video appears (recvonly transceiver)
- [ ] PiP local preview stays usable while remote is large
- [ ] Mute / camera toggle / hangup work
- [ ] Rotate / background / lock → call recovers or ends cleanly

## Conference (device)
- [ ] Join room, grid shows participants
- [ ] Late joiner video binds without restart
- [ ] Control bar reachable on small screens
- [ ] Leave room clears overlay / PiP

## Missed call → Chat (device smoke)
- [ ] Real FCM `voice-call-missed` opens Chat
- [ ] CallKit „Zurückrufen“ opens Chat + callback request
- [ ] Cold start with pending missed/callback lands in Chat
- [ ] Real FCM `morning-brief` opens Home

## Morgenbrief (device)
- [ ] Card shows check-in / chat / docs summary
- [ ] Buttons open Check-in · Chat · Docs/Aufgaben

## Regression (device)
- [ ] No automatic police / emergency dial from camera or call UI
- [ ] Arabic/RTL pass name still fits on home card
- [ ] Live-Map pin click opens Chat / Kamera-Wächter (single click)
