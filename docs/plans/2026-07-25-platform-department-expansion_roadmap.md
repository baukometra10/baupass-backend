# Plattform-Abteilungen — Schritt-für-Schritt-Roadmap

Unverändert: **kein Auto-Polizei-Notruf**. Kamera-Wächter bleibt assistiert.

## Reihenfolge

| Phase | Abteilung | Ziel | Status |
|-------|-----------|------|--------|
| **1** | Anwesenheit + Security-Inbox | Einheitliche Lage: Spät/fehlt + Security (Kamera+Zutritt) | fertig |
| **2** | HR / Verträge + Dokumente | Vorlagen-Schnellstart, Freigabe-Hinweise, Archiv-Links | fertig |
| **3** | Ops-Lagebild + Chat + Mobile | Eine Karte Leute+Kameras; Chat-Deep-Link; Push→Admin | fertig |
| **4** | Billing + Copilot + Integrationen | Usage-Klarheit; Copilot-Aktionen; Webhook-Wizard | fertig |

## Phase 1 (konkret) — erledigt

1. API `GET /api/ops-os/daily-brief` (+ Layer `13_daily_brief` in `/ops-os/overview`)
   - `attendance.lateToday`, `outsideHoursAttemptsToday`, `security.openCameraEscalations`
2. Admin-v2 Lagebild: Blöcke „Anwesenheit heute“ + „Security-Inbox“ mit Deep-Links
3. Inbox: Security-Filter enthält `camesc:*` Kamera-Eskalationen → Kamera-Wächter
4. Tests: `backend/tests/test_daily_ops_brief.py`

## Phase 2 (konkret) — erledigt

1. Verträge: Vorlagen-Schnellstart-Chips + Hinweistext (`contracts.html` / `contracts-app.js`)
2. Dokumente: Freigabe-Nächste-Schritte + Archiv-Links nach Approve/Publish (`docs.html` / `docs-app.js`)
3. Deep-Link `docs.html?status=archived` filtert Archiv

## Phase 3 (konkret) — erledigt

1. Live-Map: `cameras[]` + Chat-Deep-Link pro MA (`live_map.py`, `ops-live-map.html`)
2. Chat: `?worker_id=` / `?thread_id=` öffnet Thread nach Laden
3. Admin-Push: `admin-sw.js` navigiert Kamera-Wächter korrekt (`NAVIGATE_ADMIN_CAMERA`)
4. Lagebild: Chat-Link; Mobile ignoriert Admin-Camera-URLs weiter (Push→Admin)

## Phase 4 (konkret) — erledigt

1. Billing: Ø/MA + Tages-Nutzung (`usage-stats`) in Übersicht/Tab
2. Copilot: Quick-Actions (Lage/Spät/Security/Kamera) + deterministische DE-Antworten
3. Integrationen: Security-Webhook → Kamera-Wächter-Wizard; Teams/Slack-Schritte + Inline-Test

## Follow-up — Absenz + Inbox-Ack — erledigt

1. Daily Brief: `expectedToday` / `missingExpected` / `missingWorkers` (Einsatzplan oder Mo–Fr) ✅
2. Inbox: `camesc:*` Resolve → Kamera-Eskalation ack (Security informiert) ✅
3. **Erweiterung:** Fehlende MA als Inbox-Items `miss:{date}:{workerId}` (Quelle `attendance`) + Resolve = „Kenntnis genommen“

Unverändert: **kein Auto-Polizei-Notruf**.
