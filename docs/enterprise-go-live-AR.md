# BauPass — Enterprise Go-Live (منصة عالمية)

> **الهدف:** إطلاق إنتاجي بدون بيانات وهمية — Hybrid Flutter + FCM، بيانات حقيقية، أمان Enterprise، وقابلية توسع عالمية.

---

## Deutsch (Kurzfassung)

Dieses Runbook ist die **Go-Live-Checkliste** für eine Weltklasse-Betriebsplattform:

1. **Keine Demo-Daten** auf Railway (`BAUPASS_ALLOW_DEMO` weg oder `0`)
2. **Persistente DB** auf Volume `/data`
3. **FCM HTTP v1** für die Flutter-Mitarbeiter-App
4. **Redis + Worker** für Cron, Mahnung, Dokument-Push
5. **Geofences** mit echten Koordinaten (Ops-Karte, Digital Twin)
6. **Validierung** vor und nach Deploy (siehe unten)

---

## 1. Automatische Validierung

### Lokal / CI (nur Umgebungsvariablen)

```bash
python backend/ops/validate_enterprise_env.py
python backend/ops/validate_enterprise_env.py --strict
```

### Mit Live-API (nach Deploy)

```bash
python backend/ops/validate_enterprise_env.py --base-url https://baupass-production.up.railway.app
python backend/ops/production_cutover_check.py --base-url https://baupass-production.up.railway.app
```

### PowerShell (Windows)

```powershell
.\deploy\railway-enterprise-go-live.ps1 -BaseUrl "https://baupass-production.up.railway.app"
.\deploy\railway-health-check.ps1 -BaseUrl "https://baupass-production.up.railway.app"
```

### GitHub Actions (automatisch)

| Workflow | Wann |
|----------|------|
| `railway-deploy` | Nach jedem Push auf `main` (Job `smoke-test` + Enterprise-Validator) |
| `enterprise-go-live` | Täglich 06:00 UTC + manuell (`workflow_dispatch`) |

Repository secret **`PUBLIC_BASE_URL`** erforderlich (z. B. `https://baupass-production.up.railway.app`).

**Exit-Code `0`** = kritische Checks OK · **`2`** = vor Go-Live beheben.

Antworten live:

| Endpoint | Erwartung |
|----------|-----------|
| `GET /api/health` | `status: ok`, `enterprise.demoAllowed: false` |
| `GET /api/health/ready` | `status: ready` |
| `GET /api/platform/setup-status` | `readyScore`, `enterprise.copilotConfigured` |
| `GET /api/platform/push/status` | `fcmConfigured: true`, `fcmMode: http_v1` |

---

## 2. Railway — Pflichtvariablen (Enterprise)

Kopiere aus [`.env.railway.example`](../.env.railway.example).

| Variable | Priorität | Zweck |
|----------|-----------|--------|
| `PUBLIC_BASE_URL` | Kritisch | HTTPS-URL des Services |
| `BAUPASS_SECRET_KEY` | Kritisch | ≥32 Zeichen, zufällig |
| `BAUPASS_AUDIT_SIGNING_KEY` | Kritisch | Audit-Signatur |
| `BAUPASS_DB_PATH=/data/baupass.db` | Kritisch | Volume `/data` mounten |
| `BAUPASS_BACKUP_ON_BOOT=1` | Empfohlen | Auto-Backup |
| `REDIS_URL` | Empfohlen | Rate limit + RQ |
| `BAUPASS_DAILY_JOBS_MODE=rq` | Empfohlen | Dokument-Cron, Jobs |
| `BAUPASS_DUNNING_MODE=rq` | Empfohlen | Mahnwesen async |
| Worker-Service | Empfohlen | `python -m backend.app.tasks.worker` |
| `FCM_PROJECT_ID` + `FCM_SERVICE_ACCOUNT_JSON` | Kritisch | Hybrid-App Push (v1) |
| `FCM_V1_ONLY=1` | Nach Test | Kein Legacy-Fallback |
| `BAUPASS_WORKER_APK_URL` | Empfohlen | `join.html` APK-Link |
| `OPENAI_API_KEY` | Empfohlen | KI / Ops Copilot |
| `SMTP_*` | Empfohlen | E-Mail (Urlaub, Rechnungen) |
| `BAUPASS_CONTACT_EMAIL` | Empfohlen | Web-Push / Kontakt |
| `SENTRY_DSN` | Empfohlen | Fehlertracking |
| `BAUPASS_ALLOW_DEMO` | **Nicht setzen** | Demo-Seed in Prod gesperrt |

**Nicht in Production:**

- `BAUPASS_SEED_DEMO_ENTERPRISE=1`
- `BAUPASS_ALLOW_DEMO=1` (nur Staging)
- `FCM_SERVER_KEY` allein, wenn v1 konfiguriert ist (`FCM_V1_ONLY=1`)

---

## 3. Echte Daten — keine Platzhalter

| Bereich | Was „echt“ bedeutet |
|---------|---------------------|
| **Compliance-Score** | Berechnet aus DB (Überstunden, Dokumente, Security) |
| **Ops-Karte / Digital Twin** | Nur Geofence- + Worker-Koordinaten |
| **Posteingang** | `createdAt` aus `worker_documents` / `leave_requests` |
| **Vorarbeiter-Analytics** | `access_logs`, `worker_documents` — keine Zufallswerte |
| **Demo-Seed** | API `403` auf Railway |
| **Flutter Shifts** | `GET /api/shift/assignments` (Worker-Session) |

Mindestens **eine Geofence** pro Firma mit `latitude` / `longitude`, damit Ops Center und Live-Map vollständig sind.

---

## 4. Hybrid Mitarbeiter-App (Flutter)

1. Firebase-Projekt: Android `com.baupass.worker`, iOS gleiches Bundle
2. Echte `google-services.json` / `GoogleService-Info.plist` in CI (keine Platzhalter in Prod-Build)
3. Railway: FCM v1 Service Account
4. Worker: Login → FCM-Token → `worker_bound_devices`
5. Test-Push: Schicht zuweisen (Vorarbeiter) → App öffnet Tab **Shifts**

Dokumentation: [`mobile/docs/firebase-push-setup.md`](../mobile/docs/firebase-push-setup.md)

---

## 5. Go-Live-Checkliste (manuell)

### Vor dem Deploy

- [ ] Secrets rotiert (nicht `change-me`)
- [ ] Volume `/data` an API-Service
- [ ] Redis + Worker-Service deployed
- [ ] `validate_enterprise_env.py` ohne kritische Fehler
- [ ] Superadmin-2FA getestet (`BAUPASS_REQUIRE_SUPERADMIN_2FA=1` wenn bereit)

### Nach dem Deploy

- [ ] `railway-enterprise-go-live.ps1` Exit 0
- [ ] Login Admin v2 + Legacy
- [ ] Posteingang: Filter, Multi-Select-Bulk
- [ ] Ops Center: 12 Layer, Copilot zeigt „KI bereit“ nur mit OpenAI
- [ ] `foreman.html`: Analytics mit echten Zahlen
- [ ] Flutter: Check-in, Dokumente, Shifts, Push
- [ ] `GET /api/compliance-reports` — Score ≠ fest 85

### Woche 1 Betrieb

- [ ] Sentry-Alerts prüfen
- [ ] Backup-Alter `< 48h` (`/api/health/dr`)
- [ ] APK-URL für neue Mitarbeiter kommuniziert
- [ ] Kein Demo-Button in Admin sichtbar

---

## 6. Stufenmodell (Weltklasse-Roadmap)

| Stufe | Fokus | Status-Ziel |
|-------|--------|-------------|
| **S1 — Stabil** | DB, Redis, Health, kein Demo | `enterprise_ready` im Validator |
| **S2 — Mobil** | FCM v1, APK, Join-Flow | Push > 80 % aktiver MA |
| **S3 — Intelligent** | OpenAI, Ops Copilot, Inbox-Automation | Copilot + Agent-Tools live |
| **S4 — Global** | PG-Cutover, Multi-Region, Sentry/OTEL | Siehe `postgres-cutover-steps-AR.md` |
| **S5 — Best-in-class** | SLA, DR-Übungen, KPI-Dashboards | Quartals-Review |

Verwandte Dokumente:

- [`ENTERPRISE-CHECKLIST-AR.md`](ENTERPRISE-CHECKLIST-AR.md) — Feature-Matrix
- [`global-cloud-readiness-AR.md`](global-cloud-readiness-AR.md) — Edge, Redis, CDN
- [`stability-architecture-AR.md`](stability-architecture-AR.md) — Stabilität
- [`postgres-cutover-steps-AR.md`](postgres-cutover-steps-AR.md) — PostgreSQL

---

## 7. Support & Eskalation

| Symptom | Erste Prüfung |
|---------|----------------|
| Push kommt nicht | `/api/platform/push/status`, FCM v1, Token in App-Profil |
| Ops-Karte leer | Geofences + `mapConfigured` in Live-Map |
| Copilot „Nicht konfiguriert“ | `OPENAI_API_KEY` |
| Demo-Button sichtbar | `/api/health` → `enterprise.demoAllowed` |
| DB leer nach Restart | Volume mount + `BAUPASS_DB_PATH` |

---

*Letzte Aktualisierung: Enterprise-Härtung + Validator `backend/ops/validate_enterprise_env.py`*
