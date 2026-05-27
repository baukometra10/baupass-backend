# BauPass — قائمة الحالة الكاملة (صادقة)

## ✅ مبني ويعمل (في المنتج)

- RBAC، 2FA، عزل الشركات (tenant)
- Gates، NFC/QR، Wallet، HCE
- فواتير، dunning، موافقات، تصدير
- Worker PWA، offline sync، تعارضات sync
- Geofences (جدول + API عامل)
- حوادث، أدلة وسائط، رسائل داخلية
- تحليلات، ورديات، foreman alerts
- `/api/operations/snapshot` لوحة KPI
- Migrations، indexes، backup، audit
- Redis/RQ، rate limit، security headers
- أدوار مخصصة `/api/roles`

## ✅ أُضيف في طبقة Platform (جديد)

| الميزة | Endpoint |
|--------|----------|
| Prometheus | `GET /metrics` |
| Sentry | `SENTRY_DSN` |
| Event bus | `platform_events` + Redis |
| WebSocket | SocketIO (مع التطبيق) |
| SSE | `GET /api/v1/stream/events` |
| API v1 | `/api/v1/*` |
| API Keys | `/api/developer/api-keys` |
| Webhooks | `/api/developer/webhooks` |
| AI Assistant | `POST /api/ai/query` |
| Object storage | local / S3 |
| Geofence admin | `/api/geofences/admin` |
| Heatmap | `/api/analytics/workforce-heatmap` |
| Emergency | `/api/emergency/*` |
| Automation rules | `/api/automation/rules` |
| Integrations | `/api/integrations/*` |
| Stripe | `/api/billing/stripe/*` |
| Plugin marketplace | `/api/marketplace/plugins` |
| API catalog | `/api/marketplace/apis` |
| OCR | `POST /api/documents/ocr-analyze` |
| Expiry prediction | `/api/compliance/expiry-predictions` |
| Contractors | `/api/contractors/intelligence` |
| IoT telemetry | `POST /api/iot/devices/.../telemetry` |
| Live dashboard | `GET /api/dashboard/live` |
| Field encryption | `BAUPASS_FIELD_ENCRYPTION_KEY` |
| OpenTelemetry | `BAUPASS_OTEL=1` |
| K8s + Grafana | `deploy/k8s/`, `deploy/grafana/` |

## Physical Operations OS (12 قدرة)

راجع [`physical-operations-os-AR.md`](physical-operations-os-AR.md) — `GET /api/ops-os/overview`

| # | القدرة | API |
|---|--------|-----|
| 1 | Digital Twin | `/api/ops-os/digital-twin` |
| 2 | AI Security | `/api/ops-os/security-engine` |
| 3 | Site Intelligence | `/api/ops-os/site-intelligence` |
| 4 | Reputation | `/api/ops-os/reputation` |
| 5 | Smart Emergency | `/api/ops-os/emergency/*` |
| 6 | Camera AI | `/api/ops-os/cameras/*` |
| 7 | IoT | `/api/ops-os/iot/*` |
| 8 | Command Center | `/api/ops-os/command-center` + `ops-command-center.html` |
| 9 | Autonomous | `/api/automation/rules` |
| 10 | Workforce Graph | `/api/ops-os/workforce-graph` |
| 11 | Identity Hub | `/api/ops-os/identity` |
| 12 | Copilot | `/api/ops-os/copilot` |

## الطبقات الست المؤسسية

راجع [`enterprise-six-layers-AR.md`](enterprise-six-layers-AR.md) — `GET /api/enterprise/layers`

| # | الطبقة | الحالة |
|---|--------|--------|
| 1 | Enterprise Intelligence | ✅ |
| 2 | Integration Ecosystem | ✅ |
| 3 | Platform Ecosystem | ✅ |
| 4 | Hyper-Scale Infrastructure | ✅ |
| 5 | Security & Compliance | ✅ |
| 6 | Operational Experience | ✅ |

## إعداد خارجي (حساباتك على Railway)

- Stripe حساب تجاري + مفاتيح
- Firebase لـ FCM (اختياري)
- Grafana import من `deploy/grafana/`
- ERP field mapping حسب العميل

## بعد Deploy

```bash
python -m backend.app.migrations.runner --migrate
```

Migration **013** + **014** مطلوبة للميزات الجديدة.
