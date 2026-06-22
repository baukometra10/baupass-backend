# WorkPass – Enterprise Master Roadmap
# خارطة الطريق الشاملة للمنصة المؤسسية

> **الحالة:** مايو 2026  
> **الهدف:** منصة workforce enterprise — سريعة، قابلة للتوسع، غير تقليدية  
> **المبدأ:** نطوّر ما هو موجود، ونبني الجديد على `backend/app/` بدون كسر `server.py` أثناء الانتقال

---

## Legend | مفتاح الحالة

| Symbol | Meaning |
|--------|---------|
| ✅ | موجود ويعمل في الإنتاج |
| 🟡 | جزئي — scaffold أو docs فقط |
| 🔴 | لم يبدأ |
| ⏭ | التالي (أولوية Phase 1–4) |

---

## 1. Architecture | البنية

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| Modular Architecture (server.py split) | 🟡 ⏭ | `backend/app/` + `backend/server.py` (~24.5k lines). Blueprints: health, worker-app shim. Domains: `backend/app/domains/` |
| Domain split: Auth | 🟡 | `backend/app/api/auth.py` (stub), `domains/auth/` |
| Domain split: Workers | 🟡 | `worker_app_routes.py` delegates to server; `domains/workers/` |
| Domain split: Access / Gates | 🟡 | Gate logic in server.py; `domains/access/` |
| Domain split: Billing | 🟡 | Full invoice lifecycle in server.py; `domains/billing/` |
| Domain split: Notifications | 🟡 | Email/push in server.py; `domains/notifications/` |
| Clean Architecture (Routes → Service → Repository) | 🟡 | `repositories/base.py`, `worker_repo.py`; services layer starting |
| App Factory | ✅ | `backend/app/__init__.py` `create_app()` |
| Tenant Isolation | ✅ | `middleware/tenant.py`, `BaseRepository` |

---

## 2. Database | قاعدة البيانات

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| SQLite (production today) | ✅ | `server.py` `get_db()`, Railway `/data/baupass.db` |
| PostgreSQL support | 🟡 ⏭ | `database.py` pool + preflight; legacy SQL still sqlite3-heavy |
| Professional Indexing | ✅ | Migrations `002`, `011` — 20+ indexes |
| Migrations framework | ✅ | `migrations/runner.py`, checksum verification |
| Connection Pooling (PG) | 🟡 | `psycopg_pool` in `database.py` |
| Database Replication | 🔴 | Needs PG primary + read replica |
| Database Partitioning | 🔴 | Needs PG + time-series tables (access_logs) |
| Backup strategy | ✅ | `ops/db_backup.py`, startup backup, admin API |
| Persistence detection | ✅ | `get_database_runtime_info()`, health warnings |

**Next:** `docs/postgres-runtime-cutover.md` — cutover checklist

---

## 3. Real-Time & Events | الوقت الفعلي

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| WebSocket Real-Time | 🔴 ⏭ | Not implemented |
| Live Event Streaming | 🔴 | No SSE/WebSocket |
| Real-Time Notifications | 🟡 | Web Push (VAPID) ✅; live admin feed 🔴 |
| Real-Time Workforce Tracking | 🟡 | Geofence polling in worker-app; no live dashboard |
| Event-Driven Architecture | 🟡 | RQ queues ✅; no domain event bus |
| Event Bus System | 🔴 | Proposed: Redis Streams or NATS |
| Queue-Based Processing | 🟡 | RQ: `critical/high/default/low/scheduled/dead_letter` ✅; legacy threads still run |

---

## 4. AI & Intelligence | الذكاء الاصطناعي

| Feature | Status | Notes |
|---------|--------|-------|
| AI Workforce Intelligence Engine | 🔴 | No LLM integration |
| Predictive Attendance | 🔴 | Rule-based work hours exist; no ML |
| AI Fraud Detection | 🔴 | Anti-replay nonces ✅; no AI |
| Smart Productivity Analytics | 🔴 | Basic KPIs in admin UI |
| Behavior Pattern Analysis | 🔴 | — |
| Workforce Risk Detection | 🔴 | Document expiry alerts ✅ (rule-based) |
| Smart Operational Insights | 🔴 | — |
| AI Assistant (in-system) | 🔴 | — |
| Natural Language Queries | 🔴 | — |
| Smart Automation Engine | 🔴 | Invoice dunning automation ✅ (rules) |
| Workflow Automation Rules | 🟡 | Approval chains for invoices ✅ |
| Smart Approval Chains | ✅ | `POST /api/invoices/approvals/...` |
| Auto Employee Onboarding | 🟡 | Worker create + docs; not fully automated |
| Smart Compliance Automation | 🟡 | Document types + expiry ✅ |
| Intelligent Document Processing | 🔴 | IMAP inbox ✅; no OCR/AI |
| OCR + AI Document Analysis | 🔴 | — |
| Smart Expiry Prediction | 🔴 | Static expiry dates ✅ |

---

## 5. API Platform | منصة API

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| API Versioning | 🔴 ⏭ | All routes `/api/...` unversioned |
| Public Developer API | 🔴 | No external API docs portal |
| API Keys Management | 🟡 | Gate keys (`X-Gate-Key`) ✅; no customer API keys |
| Webhooks System | 🟡 | Gate ingest inbound ✅; no outbound webhook platform |
| API Marketplace | 🔴 | — |
| Idempotency | ✅ | `backend/app/idempotency.py` |

---

## 6. Enterprise Integrations | التكاملات

| Feature | Status | Notes |
|---------|--------|-------|
| Microsoft 365 | 🔴 | — |
| Google Workspace | 🔴 | Google Wallet pass redirect 🟡 |
| Payroll Integrations | 🔴 | Timesheets export possible manually |
| SAP / Oracle Layer | 🔴 | — |

---

## 7. Observability | المراقبة

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| Health endpoints | ✅ | `/api/health`, `/live`, `/ready`, `/queues` |
| Structured logging | ✅ | `logging_mw.py`, `emit_structured_log()` |
| System alerts | ✅ | `/api/system-alerts` |
| Gate / Invoice ops metrics | ✅ | `/api/gates/ops-metrics`, `/api/invoices/ops-metrics` |
| Prometheus Monitoring | 🔴 ⏭ | Mentioned in docs only |
| Grafana Dashboards | 🔴 | — |
| Sentry Error Tracking | 🔴 | — |
| Centralized Logging | 🟡 | JSON logs; no ELK/Loki |
| Distributed Tracing | 🔴 | No OpenTelemetry |

---

## 8. Cloud & Infrastructure | البنية السحابية

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| Docker | ✅ | `Dockerfile` |
| Railway deployment | ✅ | `railway.json`, `/data` volume |
| GitHub Actions deploy | ✅ | `.github/workflows/railway-deploy.yml` |
| Kubernetes Ready | 🟡 | Health probes ✅; no k8s manifests |
| Multi-Region Deployment | 🔴 | — |
| CDN Infrastructure | 🔴 | Static assets served from app |
| Object Storage | 🔴 | Documents in DB/filesystem |
| Edge Routing | 🔴 | — |
| Auto Scaling | 🟡 | Waitress threads; Railway scale manual |
| High Availability | 🟡 | Single container default |
| Disaster Recovery | 🟡 | SQLite backups ✅; no multi-region DR |
| Redis | 🟡 | Optional; rate limit + RQ when configured |

---

## 9. Security | الأمان

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| RBAC (roles) | ✅ | `superadmin`, `company-admin`, `turnstile`, worker session |
| RBAC tests | ✅ | `tests/test_rbac_enforcement.py` |
| 2FA (TOTP) | ✅ | `/api/me/2fa/*` |
| Security headers (CSP, HSTS) | ✅ | `middleware/security.py` |
| Rate limiting | ✅ | Redis sliding window + in-memory fallback |
| Immutable audit trail | ✅ | `audit/immutable.py`, migration `003` |
| Advanced Session Security | 🟡 | Session refresh ✅; no device binding |
| Zero-Trust Model | 🔴 | — |
| Security Audit Layer | 🟡 | Audit logs ✅; no SIEM integration |
| Encryption Layer | 🔴 | No field-level encryption yet |
| Anti-replay (gate) | ✅ | Migration `005` used_nonces |

---

## 10. Mobile & UX | تجربة الموبايل

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| Worker PWA | ✅ | `worker-app.js`, `worker-sw.js`, `emp-app.html` |
| Admin PWA | ✅ | `index.html`, `control-sw.js` |
| Ultra Fast UX (QR fast login) | ✅ | Deep link + PIN auto-submit |
| Enterprise Design System | 🟡 | Custom CSS; no shared token system |
| Cross-Platform Mobile Apps | 🔴 | PWA only |
| Advanced Offline Sync | 🟡 | Offline event queue ✅ |
| Conflict Resolution Engine | 🔴 | Basic replay only |
| Smart Device Sync | 🟡 | HCE companion registration ✅ |
| Multi-Language | ✅ | `worker-i18n.js`, admin `app.js` translations |

---

## 11. Analytics & Dashboards | التحليلات

| Feature | Status | Notes |
|---------|--------|-------|
| Live Dashboard | 🟡 | Admin panels; no WebSocket live feed |
| Workforce Heatmaps | 🔴 | — |
| Smart Analytics Engine | 🔴 | — |
| KPI Visualization | 🟡 | Access summary, invoice metrics |
| Smart Reporting | 🟡 | CSV export ✅; no report builder |

---

## 12. Access & Geofencing | الوصول والموقع

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| Gate / Turnstile API | ✅ | `/api/gates/tap`, batch, heartbeat |
| Reader adapters (ZKTeco, ACS, HID) | ✅ | `server.py` adapter classes |
| Geofencing (worker login) | ✅ | Haversine distance check |
| Industry Site Mode | ✅ | Auto check-in/out, tight radius |
| Smart Access Zones | 🟡 | Single company geofence ✅ |
| Dynamic Access Permissions | 🔴 | — |
| Temporary Visitor Access | 🟡 | Visitor flow tests exist |
| Contractor Intelligence | 🔴 | — |

---

## 13. Incidents & Alerts | الحوادث

| Feature | Status | Notes |
|---------|--------|-------|
| Smart Incident Management | 🟡 | Media evidence endpoints ✅ |
| Emergency Response Engine | 🔴 | — |
| Real-Time Alert Engine | 🟡 | System alerts table ✅; no push to admins |

---

## 14. Enterprise Platform | المنصة الموحدة

| Feature | Status | Notes |
|---------|--------|-------|
| Workforce OS Core | 🟡 | WorkPass monolith with strong features |
| Enterprise Platform SDK | 🔴 | — |
| Third-Party Extensions | 🔴 | — |
| Plugin Architecture | 🔴 | — |
| White-Label | 🟡 | Company branding/logo ✅ |
| Enterprise Tenant Isolation | ✅ | company_id enforcement |
| Multi-Region Data Isolation | 🔴 | — |
| Enterprise Compliance Layer | 🟡 | GDPR tables migration `008` ✅ |

---

## 15. Operations Intelligence | الذكاء التشغيلي

| Feature | Status | Notes |
|---------|--------|-------|
| Workforce Optimization | 🔴 | — |
| Intelligent Resource Allocation | 🔴 | — |
| AI Scheduling Engine | 🔴 | Work time config ✅ |
| Predictive Workforce Planning | 🔴 | — |

---

## 16. Communication Hub | التواصل

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| Internal Messaging | ✅ | `/api/messages` |
| Push Notifications | ✅ | Web Push VAPID |
| Smart Email Automation | 🟡 | SMTP/Brevo/Resend, IMAP poller ✅ |

---

## 17. Identity Platform | الهوية

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| QR ecosystem | ✅ | Badge QR, dynamic QR, fast login |
| NFC / HCE | 🟡 | Android HCE endpoints ✅ |
| Apple Wallet | 🟡 | `.pkpass` generation ✅ |
| Google Wallet | 🟡 | Redirect flow ✅ |
| Wallet enterprise webhooks | 🔴 | Revocation lifecycle incomplete |

---

## 18. Gate Devices & IoT | الأجهزة

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| Gate Device Management | ✅ | `/api/admin/gate-devices` |
| Device Health Monitoring | 🟡 | Heartbeat + ops metrics ✅ |
| IoT Device Infrastructure | 🟡 | Ingest API ✅; no MQTT broker |

---

## 19. SaaS Billing | الفوترة

| Feature | Status | Location / Notes |
|---------|--------|------------------|
| Subscription / Plan features | ✅ | `PLAN_FEATURES`, feature gating |
| Invoice lifecycle | ✅ | Send, retry, dunning, approvals, dead letters |
| Automated Invoice Cycles | ✅ | Monthly trigger + RQ path |
| Dunning Automation | ✅ | `run_invoice_dunning_cycle()` |
| External payment provider (Stripe) | 🔴 | Manual mark-paid only |

---

## 20. Global Expansion | التوسع العالمي

| Feature | Status | Notes |
|---------|--------|-------|
| Global Enterprise Architecture | 🔴 | Single-region Railway |
| Platform Reliability Engineering | 🟡 | Health, backups, RQ dead letter |
| Enterprise Scalability Model | 🟡 | Docs + PG path |
| Global SaaS Strategy | 🔴 | — |
| Next-Gen Workforce Infrastructure | 🟡 | This roadmap |

---

## Execution Phases | مراحل التنفيذ

### Phase 1 — Foundation (Weeks 1–4) ⏭ NOW

**Goal:** Stable, fast, maintainable core without breaking production.

1. Domain scaffold under `backend/app/domains/` (Auth, Workers, Access, Billing, Notifications)
2. Move routes incrementally: Auth → Workers → Access → Billing → Notifications
3. Activate Redis + RQ fully (retire inline threads) — see `docs/daily-jobs-rq-cutover.md`
4. Run migrations on production: `python -m backend.app.migrations.runner --migrate`
5. PostgreSQL staging cutover — see `docs/postgres-runtime-cutover.md`
6. Prometheus `/metrics` endpoint
7. Deploy retry UX (frontend) for Railway restarts

**Exit criteria:** No critical logic only in `server.py` for Auth + Health; Redis queues for all background jobs.

---

### Phase 2 — Real-Time & Platform (Weeks 5–10)

1. WebSocket layer (Flask-SocketIO or dedicated service)
2. Live admin dashboard: presence, access feed, alerts
3. Outbound webhooks platform (register, sign, retry)
4. API v1 (`/api/v1/...`) + API key management
5. Sentry + structured log shipping
6. Object storage for documents (S3/R2)

---

### Phase 3 — Enterprise & Intelligence (Weeks 11–20)

1. AI assistant (NL queries over workforce data)
2. OCR pipeline for document inbox
3. Smart expiry prediction
4. Advanced geofencing (multi-zone, visitors, contractors)
5. Stripe billing integration
6. M365 / Google Workspace connectors (SSO + calendar)

---

### Phase 4 — Global Scale (Weeks 21+)

1. Kubernetes manifests + Helm
2. Multi-region PG + read replicas
3. Partitioning for `access_logs`
4. CDN + edge routing
5. Plugin SDK + white-label packaging
6. Native mobile apps (Capacitor/React Native)

---

## Immediate Commands | أوامر فورية

```bash
# Migration status
python -m backend.app.migrations.runner --status

# Apply indexes + security tables
python -m backend.app.migrations.runner --migrate

# Start RQ worker (requires REDIS_URL)
python -m backend.app.tasks.worker

# Queue stats
python -c "from backend.app.tasks import get_queue_stats; import pprint; pprint.pprint(get_queue_stats())"
```

---

## Built in this sprint (May 2026)

| Component | Path | Status |
|-----------|------|--------|
| Platform layer | `backend/app/platform/` | ✅ scaffold + wired |
| Prometheus `/metrics` | `platform/observability/` | ✅ |
| Sentry (optional) | `SENTRY_DSN` | ✅ |
| Event bus + log | `platform/events/bus.py` | ✅ |
| SSE live stream | `GET /api/v1/stream/events` | ✅ |
| Public API v1 | `GET /api/v1/workers`, `/company`, … | ✅ |
| Developer API keys | `POST /api/developer/api-keys` | ✅ |
| Webhooks | `POST /api/developer/webhooks` | ✅ |
| AI assistant (optional) | `POST /api/ai/query` | ✅ (needs `OPENAI_API_KEY`) |
| Object storage abstraction | `platform/storage/object_store.py` | ✅ local + S3 |
| Domain modules (5) | `backend/app/domains/` | 🟡 scaffold |
| Auth logout → service | `domains/auth/service.py` | ✅ first extraction |
| Migration 013 | platform + API keys + webhooks tables | ✅ |
| K8s manifests | `deploy/k8s/deployment.yaml` | ✅ starter |
| Gate tap → event bus | `server.py` `_process_gate_tap_payload` | ✅ |

---

## Related Docs

- `docs/infrastructure-roadmap.md` — technical foundation (AR/DE)
- `docs/postgres-runtime-cutover.md` — PostgreSQL migration
- `docs/competitive-roadmap.md` — product differentiation
- `docs/enterprise-rbac-validation-report.md` — RBAC audit
- `backend/app/domains/README.md` — Clean Architecture guide
