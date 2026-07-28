# Mobile Voice / Video Call — QA Checklist

Manual device checks after one-way video + PiP/conference polish.

## 1:1 Call
- [ ] Outgoing audio connects (no auto-dial elsewhere)
- [ ] Local camera on → peer sees video
- [ ] Peer enables camera late → video appears (recvonly transceiver)
- [ ] PiP local preview stays usable while remote is large
- [ ] Mute / camera toggle / hangup work

## Conference
- [ ] Join room, grid shows participants
- [ ] Late joiner video binds without restart
- [ ] Control bar reachable on small screens

## Missed call → Chat
- [ ] Push `voice-call-missed` opens Chat (not ring UI)
- [ ] CallKit „Zurückrufen“ opens Chat + optional callback request
- [ ] Cold start with pending missed/callback keys lands in Chat

## Regression
- [ ] No automatic police / emergency dial from camera or call UI
- [ ] Arabic/RTL pass name still fits on home card
