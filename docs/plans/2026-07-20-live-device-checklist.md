# Live-Checkliste: GPS · Chat · Rechnung (Gerät)

**Datum:** 2026-07-20  
**Prod:** https://suppix-workpass-ai.up.railway.app

## GPS Auto-Checkout (3× Off-Site)
1. Mitarbeiter-App am Standort anmelden / einchecken.
2. Standort verlassen (außerhalb Geofence).
3. App offen lassen — nach **3** Off-Site-Polls (~nicht sofort nach 1) sollte Ausstempeln/Logout greifen.
4. Dashboard: Checkout / Standort verlassen sichtbar.

## Chat Unread
1. Als Admin Nachricht an Mitarbeiter senden (App im Hintergrund / nicht im Chat).
2. Quiet-Poll / Badge: Unread bleibt, bis Chat **sichtbar** geöffnet wird.
3. Chat öffnen → `mark-read` → Badge weg.

## Rechnungs-Preview
1. Rechnung öffnen → Vorschau-iframe.
2. DevTools: iframe hat `sandbox="allow-same-origin"` (kein `allow-scripts`).
3. Print/Download darf kein Raw-HTML in unsandboxed Window ausführen (nach Hardening).

## Status
- [ ] GPS 3× Off-Site (manuell)
- [ ] Chat Unread (manuell)
- [x] Code-Smoke pytest (`test_hardening_smoke_constants.py`)
