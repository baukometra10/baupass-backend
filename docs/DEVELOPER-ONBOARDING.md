# WorkPass / Suppix — Developer Onboarding

> **Ziel:** Ein mittelgroßes Team kann die Plattform erweitern, ohne `server.py` komplett neu zu lernen.

## 1. Start here (30 Minuten)

| Dokument | Inhalt |
|----------|--------|
| [`AGENTS.md`](../AGENTS.md) | Projektstruktur, Build/Test-Befehle, Commit-Stil |
| [`README.md`](../README.md) | Lokaler Start, Demo-Zugänge, API-Hinweise |
| [`backend/app/domains/README.md`](../backend/app/domains/README.md) | Domain-Blueprints, Registrierung, Migrations-Regeln |
| [`docs/HANDOVER-PLATFORM-AR.md`](HANDOVER-PLATFORM-AR.md) | Betrieb ohne Code (Railway, Kameras, Health) |
| [`docs/engineering/server-decomposition-roadmap.md`](engineering/server-decomposition-roadmap.md) | Auslagerung aus `server.py` |
| [`docs/postgres-cutover-runbook.md`](postgres-cutover-runbook.md) | SQLite → PostgreSQL Cutover |
| [`docs/postgres-staging-checklist-AR.md`](postgres-staging-checklist-AR.md) | Staging Go/No-Go vor PG-Produktion |
| [`docs/openapi/README.md`](openapi/README.md) | OpenAPI v1 — `GET /api/v1/openapi.json` |

## 2. Architektur (Kurz)

```
Root PWA (HTML/JS)     → app.js, index.html, worker-app.js
admin-v2/              → leichtes Admin-Dashboard (API v2)
backend/server.py      → Flask-Einstieg, noch viele Handler
backend/app/domains/   → API-Routing nach Fachbereich
backend/app/platform/  → Enterprise-Schichten (AI, Kameras, SSO, …)
mobile/                → Flutter Worker-App
desktop/               → Electron-Shell
deploy/                → Railway, Hetzner, Windows Service
```

**Regel:** Neue `/api/*`-Routen nur als Blueprint in `backend/app/domains/` oder `backend/app/platform/` — nicht in `server.py`.

## 3. Entwicklung lokal

```powershell
pip install -r backend/requirements.txt
python backend/server.py
# Browser: http://127.0.0.1:8000
```

```powershell
npm run test:e2e:platform   # Playwright Smoke
pytest backend/tests         # Backend (Python 3.11+ empfohlen)
```

Kopiere `.env.example` → `.env` und `.env.railway.example` für Produktion.

## 4. Sicherheit (Pflicht vor Merge)

| Thema | Wo |
|-------|-----|
| Auth / RBAC | `@require_auth`, `@require_roles` in Routes |
| CSRF / Headers | `backend/app/middleware/security.py` |
| Rate Limiting | `backend/app/middleware/rate_limiting.py` (Redis) |
| Tenant-Isolation | `company_id` in allen Queries |
| Feldverschlüsselung Chat | `BAUPASS_FIELD_ENCRYPTION_KEY` → `field_encryption.py` |
| RTSP-Bridge | `BAUPASS_RTSP_BRIDGE_TOKEN` + Header `X-WorkPass-Rtsp-Token` |

Details: [`docs/SECURITY-MODEL-AR.md`](SECURITY-MODEL-AR.md) · E2E: [`docs/E2E-VERSCHLUESSELUNG.md`](E2E-VERSCHLUESSELUNG.md), [`docs/E2E-SMOKE-TEST.md`](E2E-SMOKE-TEST.md)

## 5. Datenbank

- **Lokal:** SQLite (`backend/baupass.db`, WAL, Migrations in `backend/app/migrations/`)
- **Produktion:** SQLite auf Railway Volume **oder** PostgreSQL via `DATABASE_URL`
- Migrations: append-only, `MigrationRunner` beim Boot
- Indizes für Mandant + Zeitstempel sind vorhanden (Workers, Access, Chat, Kameras, …)

Cutover: [`docs/postgres-cutover-runbook.md`](postgres-cutover-runbook.md)  
Staging checklist: [`docs/postgres-staging-checklist-AR.md`](postgres-staging-checklist-AR.md)  
Verify script: `deploy/postgres-staging-verify.ps1`

## 6. API reference

- Live OpenAPI: `GET /api/v1/openapi.json`
- Docs: [`docs/openapi/README.md`](openapi/README.md)
- Extend [`backend/app/api/openapi_spec.py`](../backend/app/api/openapi_spec.py) when adding routes

## 7. Was ein Team als Nächstes tun sollte

1. Handler-Logik aus `server.py` in Domain-`service.py` verschieben (siehe Roadmap)
2. PostgreSQL in Staging testen, bevor Multi-Region
3. E2E-Tests ausführen: `pytest backend/tests/test_e2e_*.py` (Python 3.11+, siehe [`docs/E2E-SMOKE-TEST.md`](E2E-SMOKE-TEST.md))
4. Keine Secrets in Git — nur `.env.example`

## 7. Ist die Plattform „team-ready“?

| Kriterium | Stand |
|-----------|--------|
| Modulare API-Struktur | ✅ Domains + Platform |
| Monolith-Rest in server.py | 🟡 groß, aber dokumentiert |
| Tests | 🟡 gut für Backend-Kern, E2E smoke |
| Doku | ✅ umfangreich (DE/AR), dieser Index |
| DB | ✅ Migrations + Indizes; Postgres vorbereitet |
| Security-Baseline | ✅ Headers, CSRF, Rate limit, optional Chat-at-rest |

**Fazit:** Für ein **mittleres Team machbar**, wenn neue Features in Domains landen und `server.py` schrittweise schrumpft.

---

*Letzte Aktualisierung: Juni 2026*
