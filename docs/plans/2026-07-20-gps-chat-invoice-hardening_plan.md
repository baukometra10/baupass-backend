# Plan: Hardening Standort-GPS · Chat · Rechnungen

**Datum:** 2026-07-20  
**Kontext:** Nach Attendance A–F. Gleiches Muster: priorisierte Schwachstellen, kleine Phasen, Smoke, Deploy.

## Verdict

Höchster Nutzen: **GPS Auto-Ausstempel zu aggressiv**, **Chat-Dedup/Mute unvollständig**, **Rechnungs-Preview unsicher + schwache Betragsvalidierung**.

## Priorisierte Schwachstellen

| Prio | Bereich | Severity | Problem |
|------|---------|----------|---------|
| 1 | GPS | Hoch | Auto-Checkout schon nach 1× Off-Site-Poll (GPS-Drift) |
| 2 | GPS | Hoch | Offline/NFC kann Geofence umgehen |
| 3 | Chat | Hoch | Worker-Pfad / Push ohne durchgängiges `messageId`-Dedup |
| 4 | Chat | Hoch | Mute nur clientseitig — Push kommt trotzdem |
| 5 | Rechnung | Hoch | `renderedHtml` in unsandboxed iframe |
| 6 | Rechnung | Hoch | Line-Items: negative/huge Werte möglich |
| 7 | GPS | Mittel | site_app Login ohne GPS (QR/One-Time) — Produktentscheid |
| 8 | Chat | Mittel | GET markiert Thread als gelesen |
| 9 | Rechnung | Mittel | Stripe return-URL / webhook amount match |

## Phasen

### Phase G1 — GPS Stabilität (jetzt)
1. Server: 2–3 aufeinanderfolgende Off-Site-Samples vor Auto-Checkout (nicht nur Client-Strike).
2. Offline `site_leave`: Off-Site-Nachweis verlangen; Offline-NFC in `site_app` mit Location/Geofence.

### Phase H1 — Chat Notify (jetzt)
1. `messageId`/`threadId` in Push-Payloads + `claimChatNotifyKey` auch Worker-PWA.
2. Server: Mute vor Admin-Push prüfen.

### Phase I1 — Rechnung Sicherheit (jetzt)
1. Preview: sandboxed iframe / kein Raw-HTML aus DB ungefiltert.
2. Strikte Server-Validierung qty/unitPrice/vat/discount (finite, positiv, Caps).

### Später
- ~~site_app Login-GPS erzwingen~~ → Gate: GPS auch bei QR; site_app: Remote-Session OK, Presence nur mit GPS (`sitePresenceVerified`)
- ~~Chat mark-read von GET trennen~~ → POST `/mark-read` nur bei sichtbarem Öffnen
- ~~Stripe URL-Allowlist + amount match~~ → Return-URLs allowlisted; Paid nur bei Firma/Betrag/Währung

## Status

- [x] Phase G1 umgesetzt (2026-07-20): 3× Off-Site-Polls; Offline Leave/NFC Geofence
- [x] Phase H1 umgesetzt (2026-07-20): Worker Dedup + Mute vor Admin-Push + messageId
- [x] Phase I1 umgesetzt (2026-07-20): Sandboxed Invoice-iframes + Line-Item-Validierung
- [x] Phase G2/H2/I2 umgesetzt (2026-07-20): QR/Gate GPS, Chat mark-read, Stripe allowlist/amount

## Testplan

- [x] GPS: Leave-Schwelle Code = 3 Polls (Server + Worker) — Smoke 2026-07-20
- [x] Chat: GET markiert nicht gelesen; POST mark-read vorhanden — Smoke 2026-07-20
- [x] Rechnung: sandboxed iframe + qty-Validation — Smoke 2026-07-20
- [x] Gate-QR GPS / sitePresenceVerified Flags — Code-Review
- [x] Stripe return_url Allowlist — Smoke 2026-07-20
- [x] Prod Timestamp-Migration: Backup → dry-run → apply (Railway; 2026-07-20, 133 rows, tzIana)
- [ ] Live: 3× Off-Site → Checkout; Chat quiet-poll behält Unread; Preview ohne Script
