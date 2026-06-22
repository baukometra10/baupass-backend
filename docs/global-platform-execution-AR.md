# WorkPass — خارطة التكامل العالمي (برمجياً)

> الهدف: منصة حضور وانصراف عالمية — تكامل كامل بين Backend، Admin، تطبيق الموظف، والبوابات.

## ما هو مكتمل في الكود اليوم

| الطبقة | الحالة | ملاحظة |
|--------|--------|--------|
| API حضور/انصراف | ✅ | NFC، offline، gate scan، geofence |
| Admin Legacy (`index.html`) | ✅ | كل العمليات التشغيلية |
| Admin v2 | 🟡 | نظرة عامة، موظفون، NFC، QR، حضور مباشر |
| Flutter Worker | ✅ | NFC + offline + موقع GPS (site_app) |
| Railway SQLite | ✅ | `/data/baupass.db` |
| Enterprise APIs | ✅ | فوترة، تكاملات، مراقبة، عمليات |
| **مركز المؤسسة** | ✅ | `/enterprise-hub.html` — خريطة 16 طبقة + مساعد AI |

## مركز المؤسسة (واجهة الـ 16 طبقة)

```http
GET /api/platform/enterprise-catalog
```

واجهة: **`/enterprise-hub.html`** — لكل قدرة: `surface` + **`minPlan`** + **`enabled`** حسب خطتك + روابط UI و APIs.

تفاصيل الخطط: `docs/plans-matrix-AR.md`

## تقرير الجاهزية البرمجية

```http
GET /api/platform/capabilities
Authorization: Bearer <superadmin>
```

يعيد: `maturityScore` (0–100)، `maturityLevel`، `nextSteps`، حالة Redis، APK، قاعدة البيانات.

## المراحل نحو «منصة عالمية»

### المرحلة A — تشغيل ميداني (أسبوع 1)

1. `BAUPASS_PG_RUNTIME=0` + Volume `/data`
2. Redis على Railway + `REDIS_URL`
3. خدمة worker: `python -m backend.app.tasks.worker`
4. APK من GitHub Actions → `BAUPASS_WORKER_APK_URL`
5. اختبار موظف واحد: QR → تثبيت → NFC دخول/خروج
6. قائمة: `docs/field-test-checklist-AR.md`

### المرحلة B — إدارة موحدة (أسبوع 2–3)

1. توسيع Admin v2 (تقارير، تصدير، إعدادات موقع)
2. أو الإبقاء على Legacy للعمليات الثقيلة + v2 للتفعيل السريع
3. مراقبة: Sentry + `/api/health/ready`

### المرحلة C — توسع عالمي (شهر+)

1. `sqlite_to_postgres.py` ثم `BAUPASS_PG_RUNTIME=1`
2. Multi-region: `BAUPASS_REGION_STRATEGY=multi`
3. TestFlight / Play Store
4. تقسيم Domains من `server.py` (صيانة طويلة الأمد)

## معيار «الحلم تحقق»

- [ ] 10+ موظفين يسجلون حضوراً يومياً عبر التطبيق
- [ ] بيانات تبقى بعد redeploy
- [ ] Admin يرى الحضور المباشر والتقارير
- [ ] Redis + مهام خلفية تعمل
- [ ] APK موزّع عبر QR
- [ ] `GET /api/platform/capabilities` → `maturityLevel: production_ready` أو أعلى

---

الرؤية **موجودة في الكود**؛ الإغلاق التجاري = تنفيذ المراحل A→C على Railway وليس مزيداً من البنى النظرية.
