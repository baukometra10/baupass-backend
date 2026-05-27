# إكمال الأقسام الجزئية — ملخص التنفيذ

تاريخ: 2026-05-27

## ما اكتمل في هذه الدفعة

| القسم | التنفيذ |
|--------|---------|
| PostgreSQL analytics | `worker-trends`, `document-health`, `punctuality-report` → read replica |
| أرشفة access_logs | `archive_access_logs()` + `BAUPASS_ARCHIVE_ACCESS_LOGS_ON_BOOT` + `POST /api/ops/archive-access-logs` |
| WebSocket | اشتراك مربوط بالجلسة (`BAUPASS_WEBSOCKET_REQUIRE_SESSION`) |
| التكاملات | M365/Google sync عبر Graph/userinfo عند وجود `access_token` |
| session_devices | تسجيل عند login + فحص عند `BAUPASS_ZERO_TRUST_DEVICE_BINDING` |
| Zero-Trust | ربط الجهاز بالجلسة عند `BAUPASS_ZERO_TRUST=1` |
| تشفير الحقول | `notes` في worker_documents عند `BAUPASS_FIELD_ENCRYPTION_KEY` |
| Onboarding | `/api/v2/onboarding/*` + migration `016` |
| Auth blueprint | `/api/auth/logout` عبر AuthService |
| SSE/Events | `list_recent_events` عبر read connection |
| إصلاح | `jsonify` في realtime routes |

## ما يبقى (لاحقاً)

- تقسيم كامل لـ `server.py` (معظم الـ API)
- OAuth refresh + تخزين tokens مشفّر منفصل
- SAP/Oracle connectors إنتاجية
- Multi-region نشر فعلي
- Grafana/Loki مُثبّتة في السحابة
- تطبيقات native (خارج النطاق — PWA)

## متغيرات جديدة

راجع `.env.railway.example` — أقسام DR، archive، websocket session، field encryption.
