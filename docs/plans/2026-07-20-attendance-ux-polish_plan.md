# Plan: Anwesenheit UX Polish (J1–J7)

**Datum:** 2026-07-20  
**Kontext:** Nach Attendance A–F, GPS/Chat/Invoice G–I, Prod-Timestamp-Migration (133 Zeilen).  
**Ziel:** Ein fokussierter PR — Berlin-„Heute“, On-Site-SQL, Arbeitsstunden-Bericht formal, Admin-Karten, Display.

## Verdict

Größter Restnutzen: **UTC-„Heute“ in On-Site-Zählung**, **check-in bleibt „vor Ort“ trotz app-logout**, **Monats-Stunden zählen Presence statt formaler Arbeit + fehlendes Spillover**.

## Product Decision

**`worker_hours_summary` / `worker_timeline` = nur formale Arbeit** (`check-in` ↔ `check-out` via `pair_work_attendance_sessions`).  
`app-login`/`app-logout` bleiben Presence (Dashboard „vor Ort“, Zutritt-Feed) — nicht billable Stunden.

## Phasen

### J1 — Berlin `today_prefix`
- Datei: `backend/app/platform/physical_operations/_common.py`
- `today_prefix()` → `datetime.now(ACCESS_WALL_TZ)`; optional `reference=` für Tests
- `today_work_minutes()` yesterday ebenfalls Berlin

### J2 — On-Site SQL respektiert `app-logout`
- Datei: gleiches `_common.py`, `_present_on_site_sql_body()`
- Offene `check-in`-Session schließen bei späterem `direction IN OFF_SITE_DIRECTIONS` (nicht nur `check-out`)

### J3 — Formal hours + Spillover-Parität
- Dateien: `companies/service.py`, `companies/repository.py`
- `pair_presence_sessions` → `pair_work_attendance_sessions` in summary + timeline
- Summary: Spillover-Tage ±1 wie Timeline; shared `_session_overlaps_month` Helper
- `daysWorked` auf attributed Arbeitstag

### J4 — `/api/access-logs/summary` Berlin + Presence-Buckets
- Datei: `backend/server.py` `access_summary()`
- `_parse_access_timestamp` statt `parse_iso_utc`; Berlin-today für Late-Check
- Hourly: zusätzliche Felder `appLogin` / `appLogout` (nicht mit checkIn mischen)

### J5 — admin-v2 Karten
- Dateien: `admin-v2/app.js`, `admin-v2/i18n-strings.js`
- Zwei zusätzliche Karten Standort-Login / -Logout (de/en/ar)

### J6 — Access-Timestamp Display in `app.js`
- `formatAccessTimestamp` + 5 Call-Sites; `timeZone` in Clock/Day-Labels für historische `Z`-Rows

### J7 — Tests
- `test_presence_sessions.py`: Berlin today_prefix, check-in+app-logout → nicht vor Ort, hours formal-only, spillover summary
- Optional light `access_summary` hour-bucket Assert

## Nicht jetzt

- GPS Leave / Timestamp-Parser Core
- ~10 weitere inline `today`-Duplikate in `server.py` (Fast-follow)
- `formatTimestamp` für Non-Access-Daten
- Alle 8 i18n-Sprachen für neue Keys

## Testplan

- [ ] `pytest` Presence/Hours-Tests grün
- [ ] Manuell: admin-v2 Access-Karten; Worker-Detail; Timeline; „Jetzt vor Ort“ nach app-logout
- [ ] Edge: Browser-TZ ≠ Berlin — Access-Zeiten korrekt

## Status

- [x] Plan bestätigt → Implementierung (2026-07-20)
- [x] J1–J7 umgesetzt; pytest presence + hours formal grün
