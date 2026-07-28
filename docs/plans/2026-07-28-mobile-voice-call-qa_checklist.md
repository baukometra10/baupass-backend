# Mobile Voice / Video Call — QA Checklist

Manual device checks after one-way video + PiP/conference polish.

**Devices:** Android 13+ · iOS 16+ · at least one low-end phone.

## 1:1 Call
- [ ] Outgoing audio connects (no auto-dial elsewhere)
- [ ] Local camera on → peer sees video
- [ ] Peer enables camera late → video appears (recvonly transceiver)
- [ ] PiP local preview stays usable while remote is large
- [ ] Mute / camera toggle / hangup work
- [ ] Rotate / background / lock → call recovers or ends cleanly

## Conference
- [ ] Join room, grid shows participants
- [ ] Late joiner video binds without restart
- [ ] Control bar reachable on small screens
- [ ] Leave room clears overlay / PiP

## Missed call → Chat
- [ ] Push `voice-call-missed` opens Chat (not ring UI)
- [ ] CallKit „Zurückrufen“ opens Chat + optional callback request
- [ ] Cold start with pending missed/callback keys lands in Chat
- [ ] Push `morning-brief` opens Home (not Chat)

## Morgenbrief (Home)
- [ ] Card shows check-in / chat / docs summary
- [ ] Buttons open Check-in · Chat · Docs/Aufgaben

## Regression
- [ ] No automatic police / emergency dial from camera or call UI
- [ ] Arabic/RTL pass name still fits on home card
- [ ] Live-Map pin click opens Chat / Kamera-Wächter (single click)
