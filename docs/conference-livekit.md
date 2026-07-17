# Firmenkonferenz & Admin-Call (chat41)

## Env (LiveKit Cloud)

```env
LIVEKIT_URL=wss://YOUR_PROJECT.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
```

Ohne Keys: API liefert `503 livekit_not_configured`; Admin zeigt Hinweis. 1:1 Calls bleiben unabhängig.

## Admin

- 1:1 Call-Overlay redesigned (Topbar, Teilnehmer-Rail, Invite, Kamera, Notiz, ICE-Diag)
- Button **Konferenz** startet Room + lädt aktuellen Worker ein
- Mid-call **+ Einladen** (Multi-Select)

## Worker PWA / Flutter

- Poll `/api/worker-app/chat/conferences/incoming`
- Join via LiveKit token (PWA: `chat-conference.js`; Flutter: Invite-Sheet + Token)

## Kosten

Siehe Plan: LiveKit Cloud participant-minutes (Video 50–100 Personen).
