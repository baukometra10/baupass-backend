# Call sounds (WhatsApp-like)

Directions must never share the same clip.

| File | When | Character |
|------|------|-----------|
| `phone-call-ring.mp3` | **Incoming** (someone calls you) | Short melodic messenger motif + silence (~2.45s) |
| `phone-call-ringback.mp3` | **Outgoing** (you call someone) | Classic dual-tone ringback 440+480 “tring-tring” + ~4s pause (~5s) |
| `phone-call-ring-cycle.mp3` | Alias of ringback | Older cache URLs |

Mobile:

- `mobile/assets/sounds/incoming_ring.mp3` ← incoming motif  
- `mobile/assets/sounds/outgoing_ringback.mp3` ← ringback  

Regenerate:

```bash
python sounds/_gen_wa_rings.py
ffmpeg -y -i sounds/_incoming_wa.wav -codec:a libmp3lame -qscale:a 4 sounds/phone-call-ring.mp3
ffmpeg -y -i sounds/_outgoing_wa.wav -codec:a libmp3lame -qscale:a 4 sounds/phone-call-ringback.mp3
```

Original motifs (not WhatsApp copyrighted audio).
