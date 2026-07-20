# Live-Checkliste: GPS · Chat · Rechnung · Lage · Wallet (Gerät)

**Datum:** 2026-07-20  
**Prod:** https://suppix-workpass-ai.up.railway.app

## Automatisiert (Code)
- [x] GPS 3× Off-Site-Polls: `test_worker_site_geofence_api.py` + `test_hardening_smoke_constants.py`
- [x] Invoice sandbox Konstanten: `test_hardening_smoke_constants.py`
- [x] Compliance Berlin-Expiry: `test_autopilot_doc_expiry_berlin.py`
- [x] Lage realtime: Overview refreshed on access/inbox/camera events (`admin-v2`)

## GPS Auto-Checkout (3× Off-Site) — Gerät
1. Mitarbeiter-App am Standort anmelden / einchecken.
2. Standort verlassen (außerhalb Geofence).
3. App offen lassen — nach **3** Off-Site-Polls (~nicht sofort nach 1) sollte Ausstempeln/Logout greifen.
4. Dashboard: Checkout / Standort verlassen sichtbar.

## Chat Unread — Gerät
1. Als Admin Nachricht an Mitarbeiter senden (App im Hintergrund / nicht im Chat).
2. Quiet-Poll / Badge: Unread bleibt, bis Chat **sichtbar** geöffnet wird.
3. Chat öffnen → `mark-read` → Badge weg.

## Rechnungs-Preview
1. Rechnung öffnen → Vorschau-iframe.
2. DevTools: iframe hat `sandbox="allow-same-origin"` (kein `allow-scripts`).

## Live-Lage (Admin)
1. Overview öffnen — Panel „Live-Lage 2030“ sichtbar (Badge Live/Aktualisiert).
2. Check-in eines Mitarbeiters → KPI „Vor Ort“ / Check-ins aktualisiert ohne manuellen Reload.
3. Inbox-Dokument-Reminder → KPI Aufgaben aktualisiert.

## Wallet
1. Platform-Tab: Apple/Google Runtime-Status (grün nur mit Zertifikaten).
2. Worker-App: Wallet-Button — bei fehlender Config klare 503-Meldung; QR bleibt nutzbar.
3. Mit Zertifikaten: Add to Apple/Google Wallet öffnet Pass.

## Status
- [ ] GPS 3× Off-Site (manuell Gerät)
- [ ] Chat Unread (manuell Gerät)
- [x] Code-Smoke GPS 3× Contract
- [x] Lage realtime Wiring
- [x] Wallet readiness Gate + Platform Status UI
