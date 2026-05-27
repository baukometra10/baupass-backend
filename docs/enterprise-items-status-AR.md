# حالة البنود — جزئي 🟡 مقابل لم يُبدأ 🔴

**تطبيق الموظف Hybrid (BauPass Worker):** ليس تطبيق متجر عام (BWA). التوزيع من **داخل النظام**:
- **PWA:** `emp-app.html` + `worker-install.html` (تثبيت من المتصفح)
- **Flutter/Hybrid:** `mobile/` — NFC + RFID على القارئ/الهاتف، ثلاثة أوضاع (QR، بطاقة فيزيائية، HCE) عبر `/api/worker-app/*`
- **روابط من Admin:** QR تفعيل، `BAUPASS_WORKER_APK_URL`, `/worker-join-config.json`
- **API موحّد:** `GET /api/v2/mobile/distribution`
- **معمارية:** [`docs/enterprise-hybrid-platform-AR.md`](enterprise-hybrid-platform-AR.md)

### الأوضاع الثلاثة (Hybrid)

| الوضع | الوصف |
|--------|--------|
| 1 | تطبيق Hybrid: QR أو Badge + PIN (`/api/worker-app/login`) |
| 2 | بطاقة NFC/RFID على **قارئ البوابة** (`/api/scan`) |
| 3 | HCE — الهاتف كبطاقة على Android (`/api/worker-app/hce`) |

---

## 🟡 جزئي — لم يُكمل بعد (يُنهى في الكود أولاً)

| # | البند | ما ينقص |
|---|--------|---------|
| 1 | Modular Architecture | نقل أغلب مسارات `server.py` (~25k سطر) إلى domains |
| 2 | Domains كاملة | Auth/Workers/Access/Billing/Notifications — v2 موجود، legacy ما زال في server |
| 3 | Clean Architecture | repositories لكل aggregate |
| 4 | PostgreSQL كامل | تفعيل Railway + `BAUPASS_PG_REQUIRED` + مراجعة كل SQL |
| 7 | Database Replication | replica على المزيد من التقارير؛ خدمة Postgres replica على Railway |
| 20 | Behavior Pattern Analysis | ✅ `/api/analytics/behavior-patterns` |
| 29–31 | M365 / Google / Payroll | ✅ sync + OAuth مشفّر |
| 32 | SAP / Oracle | health عند base_url؛ ERP كامل لاحقاً |
| 36 | Centralized Logging | نشر Loki/ELK + `BAUPASS_LOG_FORWARD_URL` |
| 37 | Distributed Tracing | agent OpenTelemetry في الحاوية |
| 40 | CDN | شبكة CDN أمام Railway (Cloudflare) |
| 42 | Edge Routing | توجيه جغرافي فعلي |
| 43–44 | Auto Scaling / HA | HPA على K8s أو توسيع Railway يدوي |
| 49 | Zero-Trust | سياسات mTLS/posture كاملة |
| 52 | Encryption Layer | تشفير حقول إضافية (ليس `notes` فقط) |
| 55 | Design System | tokens موحّدة admin + worker |
| 72–73 | OCR + AI | pytesseract اختياري + تحسين pipeline |
| 83 | Workforce OS Core | فصل monolith تدريجي |
| 85 | Third-Party Extensions | sandbox plugins |
| 94–97 | Operations Intelligence | تحسين جدولة/تخصيص موارد |
| 113, 115–117 | Global / Strategy | وثائق + تنفيذ سحابي |

---

## 🔴 لم يُبدأ أو يحتاج بنية خارجية

| # | البند | السبب |
|---|--------|--------|
| 39 | Multi-Region إنتاجي | منطقتان + DB replication + DNS |
| 90 | Multi-Region Data Isolation | سياسة residency per tenant |
| 31–32 (إنتاج) | Payroll / SAP / Oracle كامل | موصلات ERP معتمدة + عقود API |
| 56 (متاجر عامة) | App Store / Play Store عام | **خارج النطاق** — التوزيع الداخلي من النظام ✅ |
| Grafana/Sentry/Loki | مراقبة مُدارة | حسابات ولوحات خارج الكود |

---

## ✅ مكتمل تشغيلياً (مرجع سريع)

البنود 5–6, 8–19, 21–28, 33–35, 38, 41, 45–48, 50–51, 53–54, 57–71, 74–82, 84, 86–89, 91–93, 98–112, 114 — راجع `ENTERPRISE-CHECKLIST-AR.md`.

---

## ترتيب التنفيذ المعتمد

1. إغلاق كل 🟡 في الكود (هذه الدفعة + التالية)
2. ثم 🔴 التي تحتاج قرارك (Railway multi-DB، ERP، CDN)
3. تطبيق الموظف Hybrid = PWA (`emp-app`) + Flutter (`mobile/`) + NFC/RFID/HCE — **ليس BWA**
