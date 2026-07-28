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

## Follow-up — Schichten / Firmenzeiten (flexibel) — erledigt

1. Firmen-Arbeitsbeginn/-ende wieder editierbar (Tools) — leer = flexibel, keine festen Schichten ✅
2. Absenz-Grace nutzt Einsatzplan-Zeit → Firmenzeit → sonst kein Mo–Fr-Spam ✅
3. Daily Brief `workWindow` + Lagebild-Anzeige ✅
4. Einsatzplan: „Firmenzeiten“ auf leere Tage + Rotation optional mit Firmenzeiten ✅

## Follow-up — Chat + Calls (Ops-Loop) — erledigt

1. Daily Brief `chat`: verpasste eingehende Anrufe + Rückruf-Anfragen ✅
2. Inbox: `vcall:{callId}` / `vcallcb:{callId}` (Quelle `chat`) + Resolve = „Kenntnis genommen“ ✅
3. Lagebild: KPI + Block „Chat & Anrufe“ mit Deep-Link; Filter-Chip Chat ✅
4. Inbox-Refresh bei Missed/Callback (`notify_inbox_changed`) ✅

## Follow-up — HR Mini-Loop (Urlaub + Docs) — erledigt

1. Daily Brief `hr`: `pendingLeave` + `expiringDocuments` (14 Tage) ✅
2. Lagebild: KPI + Block „HR · Urlaub & Dokumente“ mit Inbox-Deep-Links ✅
3. Startup `?tab=inbox&source=leave|document` setzt Inbox-Filter ✅

## Follow-up — Copilot ↔ Daily Brief — erledigt

1. Copilot-Kontext enthält Slim-`dailyBrief` (Anwesenheit/Security/Chat/HR) ✅
2. Deterministische Antworten für Lage, Spät/fehlt, Chat/Anrufe, Urlaub/Docs ✅
3. Quick-Actions Chat/Anrufe + Urlaub & Docs; Tagesbriefing nutzt Brief-KPIs ✅

## Follow-up — Docs in_review im Ops-Loop — erledigt

1. Daily Brief `hr.inReviewDocuments` aus `editor_documents` (Status `in_review`) ✅
2. Inbox `edoc:{id}` (Quelle `document`) + Deep-Link `docs.html?status=in_review` ✅
3. Lagebild/Copilot zeigen „In Prüfung“ — **kein Auto-Approve** ✅

## Follow-up — Mobile Push → Chat/Anruf — erledigt

1. Tag `voice-call-missed` öffnet Chat (nicht Klingel-UI) inkl. Deep-Link `baupass://app/chat?missed=1` ✅
2. CallKit „Zurückrufen“ → Chat + optional Auto-Callback-Request ✅
3. Cold-start Pending Keys für Missed/Callback ✅

## Follow-up — Autopilot Soft-Hints (HR) — erledigt

1. Täglicher Hinweis bei offenen Urlaubsanträgen (`autopilot.leave_queue`) — **kein Auto-Approve** ✅
2. Täglicher Hinweis bei Docs `in_review` (`autopilot.docs_review`) — **kein Auto-Approve** ✅
3. Admin-Toggles + Inbox-Deep-Links ✅

## Follow-up — Soft-Hints Absenz + Security — erledigt

1. Hinweis fehlende erwartete MA (`autopilot.missing_expected`) — **kein Auto-Dial** ✅
2. Hinweis offene Security/Kamera (`autopilot.security_open`) — **kein Auto-Polizei** ✅
3. Admin-Toggles + Inbox/Live-Map Deep-Links ✅

## Follow-up — Worker-Morgenbrief + Live-Map + Smoke — erledigt

1. `GET /api/worker-app/morning-brief` + Mobile Home-Card ✅
2. Live-Map: Doppelklick Pin → Chat/Wächter, Status mit fehlt/Alarm ✅
3. Smoke: Brief→Inbox→Live-Map→Copilot (pytest + platform-smoke) ✅
4. Docs-i18n 8 Sprachen regeneriert; Mobile Call QA-Checkliste ✅

Unverändert: **kein Auto-Polizei-Notruf** · **kein Auto-Dial** bei Anrufen · **kein Auto-Approve** für Docs/Urlaub · Zeiten entscheidet jede Firma selbst.
