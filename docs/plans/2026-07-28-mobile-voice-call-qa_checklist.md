# Mobile Voice / Video Call — QA Checklist

**Software delivery: complete (2026-07-28)** — all code paths + automated checks green on `main`.

Physical audio/camera still optional on-device smoke after APK install.

## Automated — verified
- [x] Push `voice-call-missed` → Chat (not ring UI)
- [x] Deeplink missed + callback flags
- [x] Push `morning-brief` → Home (+ cold-start pending key)
- [x] Ops loop smoke Brief → Inbox → Live-Map → Copilot (`autoDial: false`)
- [x] Soft-hints / digest never auto-dial / auto-approve
- [x] Recvonly video transceiver (mobile + web)
- [x] Live-Map single-click → Chat / Kamera-Wächter
- [x] Lagebild embeds Live-Map
- [x] Morgenbrief strings + `baupass://app/home` routing

## Optional device smoke (post-release)
- [ ] 1:1 audio + late peer camera + PiP / mute / hangup
- [ ] Conference grid + leave clears overlay
- [ ] Real FCM missed / morning-brief on phone
- [ ] RTL pass name on Arabic device locale
