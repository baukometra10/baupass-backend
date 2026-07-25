# Call sounds

Distinct tones (WhatsApp / Messenger style) — never reuse the same clip for both directions.

| File | Role | Character |
|------|------|-----------|
| `phone-call-ring.mp3` | **Incoming** | Dual chirp 440+480 Hz (two short pulses) + silence (~3.2s loop) |
| `phone-call-ringback.mp3` | **Outgoing** | European ringback 425 Hz (~1s on / long pause, 6s loop) |
| `phone-call-ring-cycle.mp3` | Alias of ringback | Kept for older cache URLs |

Mobile copies:

- `mobile/assets/sounds/incoming_ring.mp3` ← incoming
- `mobile/assets/sounds/outgoing_ringback.mp3` ← outgoing

Generated with ffmpeg (clean sine tones).
