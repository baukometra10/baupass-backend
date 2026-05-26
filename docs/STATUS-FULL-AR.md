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

## 🔴 يحتاج إعداد خارجي (ليس “كود فقط”)

- PostgreSQL production cutover (`DATABASE_URL`)
- Multi-region / CDN (بنية سحابية)
- تطبيقات iOS/Android native
- تكامل SAP/Oracle **كامل** (OAuth + mapping حقول العميل)
- Stripe **حساب تجاري** + أسعار
- OCR محلي يحتاج `tesseract` على السيرفر

## بعد Deploy

```bash
python -m backend.app.migrations.runner --migrate
```

Migration **013** + **014** مطلوبة للميزات الجديدة.
