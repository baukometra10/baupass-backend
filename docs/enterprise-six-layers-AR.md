# الطبقات الست للمؤسسة — BauPass

## 1) Enterprise Intelligence Layer

**الهدف:** المنصة «تفكر» — تحليل، تنبؤ، احتيال، إنتاجية، مخاطر، تحسين موارد.

| القدرة | API |
|--------|-----|
| حزمة موحّدة | `GET /api/enterprise/layers/intelligence` |
| رؤى تشغيلية | `GET /api/ai/intelligence` |
| تنبؤ حضور | `GET /api/ai/predictive-attendance` |
| احتيال | `GET /api/ai/fraud-detection` |
| أنماط سلوك | `GET /api/analytics/behavior-patterns` |
| تحسين موارد | `GET /api/operations/intelligence/*` |
| مساعد AI | `POST /api/ai/query` |

**الحالة:** ✅ مفعّل في الكود (قواعد + LLM اختياري بـ `OPENAI_API_KEY`).

---

## 2) Enterprise Integration Ecosystem

**الهدف:** BauPass مركز التشغيل — ERP، رواتب، M365، Google، بوابات، IoT، كاميرات.

| التكامل | API |
|---------|-----|
| كatalog + حالة | `GET /api/enterprise/layers/integrations` |
| ربط | `POST /api/integrations/{provider}/connect` |
| مزامنة | `POST /api/integrations/{provider}/sync` |
| كاميرات أمن | `POST /api/integrations/security-cameras/events` |
| قارئ بصمة/بيومترية | `POST /api/integrations/biometric/events` |
| بوابات | `/api/scan`, `/api/gates/tap`, `/api/device/ingest` |

**الحالة:** ✅ M365/Google/Payroll/SAP·Oracle + أجهزة؛ ERP mapping حسب العميل.

---

## 3) Platform Ecosystem Layer

**الهدف:** من Software إلى Platform — APIs، SDK، Plugins، Marketplace.

| مكوّن | مسار |
|--------|------|
| حالة الطبقة | `GET /api/enterprise/layers/platform` |
| API v1/v2 | `/api/v1/*`, `/api/v2/*` |
| مفاتيح مطورين | `/api/developer/api-keys` |
| Webhooks | `/api/developer/webhooks` |
| Marketplace | `/api/marketplace/plugins` |
| SDK Python | `sdk/baupass_client.py` |

**الحالة:** ✅

---

## 4) Hyper-Scale Infrastructure Layer

**الهدف:** آلاف الشركات وملايين العمليات — K8s، multi-region، CDN، HA.

| مكوّن | مسار / ملف |
|--------|------------|
| حالة الطبقة | `GET /api/enterprise/layers/infrastructure` |
| K8s | `deploy/k8s/` |
| Multi-region | `docs/multi-region-deployment-AR.md` |
| DR | `GET /api/health/dr` |
| PostgreSQL | `GET /api/platform/database-status` |

**الحالة:** ✅ كود + manifests؛ نشر منطقتين = تشغيل سحابي.

---

## 5) Enterprise Security & Compliance Layer

**الهدف:** Zero Trust، تشفير، audit، SIEM، RBAC، امتثال.

| مكوّن | مسار |
|--------|------|
| حالة الطبقة | `GET /api/enterprise/layers/security` |
| SIEM export | `GET /api/enterprise/security/siem-export` |
| Zero-Trust | `BAUPASS_ZERO_TRUST=1` |
| تشفير حقول | `BAUPASS_FIELD_ENCRYPTION_KEY` |
| RBAC | `/api/roles` |
| Audit | `audit_logs` + immutable |

**الحالة:** ✅

---

## 6) Operational Experience Layer

**الهدف:** UX عالمي، سرعة، real-time، Hybrid mobile.

| مكوّن | مسار |
|--------|------|
| حالة الطبقة | `GET /api/enterprise/layers/experience` |
| Hybrid Worker | `GET /api/v2/mobile/distribution` |
| PWA | `emp-app.html` |
| Design tokens | `/design-tokens.css` |
| WebSocket / SSE | SocketIO + `/api/v1/stream/events` |

**الحالة:** ✅

---

## نقطة دخول واحدة

```http
GET /api/enterprise/layers
Authorization: Bearer <session>
```

يعيد الست طبقات مع `status: active` لكل منها.
