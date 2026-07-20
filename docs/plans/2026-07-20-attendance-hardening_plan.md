# Plan: Gemeinsame Kontrolle — Schwachstellen verstärken

**Datum:** 2026-07-20  
**Kontext:** Nach den Fixes zu Monatsauswertung, Auto-Ausstempel, Posteingang-Piep und Zutritt-Sortierung.

## Verdict

Die größten Rest-Risiken liegen bei **gemischten Zeitstempeln (UTC vs lokal)**, **unvollständiger App-Login-Behandlung** und **falschen „Heute“-Filtern**. Der Posteingang-Piep ist weitgehend gefixt; Chat-Ton im offenen Chat-Fenster piept noch zu früh.

## Priorisierte Schwachstellen

| Prio | Severity | Problem | Ort |
|------|----------|---------|-----|
| 1 | Hoch | Session-Dauer falsch, wenn `…Z` mit lokalem Stempel gepaart wird | `_common.py` `_parse_access_timestamp` / `minutes_between_*` |
| 2 | Hoch | „Heute“-Liste / Presence nutzt UTC-Tag statt Berlin | `app.js` `renderRecentAccess`, `getTodayPresenceMeta` |
| 3 | Hoch | Tor-Karten zählen nur `check-in`/`check-out`, nicht App-Login | `app.js` `renderAccessSummary` |
| 4 | Hoch | Auto-Close nur bei `check-in`, nicht `app-login` | `server.py` `auto_close_*` |
| 5 | Mittel | Monatsauswertung verliert Overnight über Monatsgrenze | `companies/service.py` `worker_timeline` |
| 6 | Mittel | Chat piept auch wenn Admin schon im Chat fokussiert ist | `chat-realtime.js` `notifyAdminWorkerMessage` |
| 7 | Mittel | Doppel-Piep Push + Realtime möglich | `chat-global-notify.js` |

## Status

- [x] Phase A+B umgesetzt (2026-07-20): Timestamp-Normalisierung Berlin, Zutritt-UI Heute/App-Login, Chat-Ton still im fokussierten Chat
- [x] Phase C umgesetzt (2026-07-20): Auto-Close inkl. app-login/app-logout; Monats-Timeline Overnight-Spillover
- [x] Phase D umgesetzt (2026-07-20): Push/Socket Dedup (45s) für Chat- und Anruf-Benachrichtigungen

## Empfohlener Ansatz (Top-3 zuerst)

### Phase A — Zeitstempel kanonisch machen (Kern)

1. In `_parse_access_timestamp`: naive Stamps als Europe/Berlin interpretieren; `Z`/Offset als UTC → Berlin normalisieren, dann vergleichen.
2. Gleiche Normalisierung in Frontend `minutesBetweenAccessTimestamps` / Presence, wo nötig.
3. Auto-Checkout weiter als **lokale Wanduhr** ohne `Z` schreiben (bereits so); bestehende Repair-Logik belassen.

### Phase B — Zutritt-UI konsistent

1. `renderAccessSummary`: `app-login` → Eintritt, `app-logout` → Austritt (gleiche Hilfen wie Presence).
2. `getTodayPresenceMeta` + Filter: Kalendertag Europe/Berlin, nicht `toISOString().slice(0,10)`.
3. Kurz testen: GPS manuell + Standort-Login erscheinen korrekt in Tor-Karten und „Heute“.

### Phase C — Auto-Close & Monatsrand

1. Open-Session-Query: letztes Event `check-in` **oder** `app-login` ohne späteren Off-Site.
2. `worker_timeline`: Spillover vom Vormonats-Check-in behalten, wenn Checkout im Zielmonat; dem Check-in-Tag / Schichttag zuordnen.

### Phase D — Chat-Ton (klein, schnell)

1. Sound erst nach Guard `focused && onChatPage` — bei fokussiertem Chat: still.
2. Optional: kurze Dedup-Map `messageId`/`threadId` (z. B. 30s) zwischen SW-Push und Socket.

## Nicht jetzt

- Großes Timestamp-Migrations-Skript für die ganze DB
- Posteingang-UX Umbau über Label hinaus
- Neue Features außerhalb Attendance/Notify

## Testplan

- [x] Pairing: Check-in `…Z` + Auto-Checkout lokal → Dauer ≈ Schichtende − Check-in (kein +2h Fehler) — Smoke 2026-07-20 (289 min)
- [x] Zutritt-Zusammenfassung: App-Login erhöht „Eintritte“ — Code `isAccessArrivalDirection` + Smoke
- [x] „Heute“ zeigt Buchungen ab Mitternacht Berlin, auch wenn UTC noch Vortag ist — Smoke Berlin-Tag
- [x] Overnight 17:00–02:00: Auto-Ausstempel bei Schichtende (`timestamp_value=checkout_ts`), nicht wall-clock „jetzt“ — Code-Review
- [x] Monatsauswertung am 1.: Spillover Vormonat → Zielmonat — Smoke Attribution
- [x] Chat-Seite fokussiert: kein Piep; Push/Socket Dedup 45s — Code-Review Phase D

## Umsetzungsreihenfolge

1. Phase A + B (größter User-Nutzen, ein PR)
2. Phase C
3. Phase D

Geschätzter Umfang: ~1 fokussierter PR für A+B+D, optional zweiter für C.
