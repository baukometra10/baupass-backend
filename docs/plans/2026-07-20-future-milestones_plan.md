# Plan: Future Milestones — Command Center · Wallet/Gate · Compliance Autopilot

**Datum:** 2026-07-20  
**Kontext:** Nach Attendance-/Ops-Hardening; Zielbild „bestes Future“.  
**Scope:** Drei Flagship-Bets mit bestehenden APIs, minimale Backend-Erweiterung.

## Verdict

Umsetzung über **bestehende Snapshot-/Inbox-/Wallet-/Autopilot-APIs**, UI-Verdichtung in admin-v2 + Worker-App, Berlin-Kalender für Doc-Expiry im Autopilot.

## Phasen

### F1 — Command Center 2030 (Live-Lage)
- `admin-v2`: Panel `#lagePanel` auf Overview
- Daten: `/api/operations/snapshot`, Ops-OS Brief, `/api/integrations/cameras`, Inbox-Counts
- KPIs: Vor Ort · Check-ins heute · Kameras online · Security · offene Inbox
- Deep Links: KI Command Center (autoprompt), Ops Center, Live-Karte, Anwesenheit, Inbox

### F2 — Wallet + Gate
- Flutter `DigitalCardRepository.requestWalletPass(platform)` → `GET /api/worker-app/wallet/pass`
- Home: Apple/Google-Wallet-Buttons unter Digital Pass; QR bleibt Gate-Fallback; NFC separat
- Backend-Wallet-Endpunkte unverändert (bereits vorhanden)

### F3 — Compliance Autopilot
- Inbox-Karte `#complianceAutopilotCard`: Ablauf-Count, Reminder-Bulk, Autopilot-Run
- `runner._auto_notify_document_expiry`: Berlin `today_prefix` / `calendar_day_offset`
- Nach erfolgreichen Pushes: `notify_inbox_changed(..., source="document_expiry")`

## Nicht im Scope
- Neue Wallet-Signing-Infrastruktur / NFC-Pass-Provisioning
- Eigenes Lage-Backend (weiterhin Aggregation bestehender Endpunkte)

## Done when
- [x] Lage-Panel sichtbar und klickbar
- [x] Wallet-Buttons in Worker-Home
- [x] Compliance-Karte + Berlin-Expiry + Inbox-Notify
- [x] Plan-Doku
