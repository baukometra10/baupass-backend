# WorkPass — وثيقة تسليم المنصة (Handover)

> **الهدف:** منصة **جاهزة للتشغيل في أي وقت** عبر Railway + لوحة التحكم + وكيل الكameras المحلي — **بدون فتح الكود أو تعديله** للعمليات اليومية.

**آخر تحديث:** يونيو 2026 · يشمل نظام الكameras الكامل (RTSP، مراقبة، PDF، تقرير ليلي)

---

## 1. مبدأ التسليم

| ما يُفعل **بدون كود** | ما يحتاج **مطوّر** (نادر) |
|----------------------|---------------------------|
| إضافة شركات / عمال / أجهزة | تغيير منطق أعمال جديد |
| تفعيل الكameras + RTSP Agent | ميزة غير موجودة في المنصة |
| SMTP، FCM، Redis عبر Railway Variables | إصلاح bug في الإنتاج |
| تقارير PDF، تنبيهات، inbox | تخصيص واجهة من الصفر |
| النشر التلقائي من GitHub → Railway | — |

**قاعدة:** كل ما تحتاجه للتشغيل اليومي موجود في **Railway Variables** أو **WorkPass / admin-v2** أو **سكربت الوكيل على موقع البناء**.

---

## 2. فحص الجاهزية (مرة واحدة + بعد كل نشر)

```powershell
cd C:\Users\u4363\Desktop\baustelle
powershell -ExecutionPolicy Bypass -File .\deploy\handover-ready.ps1 -BaseUrl "https://baupass-production.up.railway.app"
```

أو يدوياً:

```powershell
.\deploy\railway-cli-status.ps1
.\deploy\railway-enterprise-go-live.ps1 -BaseUrl "https://YOUR_APP.up.railway.app"
```

**Exit code 0** = المنصة جاهزة للتسليم والتشغيل.

| Endpoint | المعنى |
|----------|--------|
| `GET /api/health` | السيرفر + DB + Redis |
| `GET /api/health/ready` | جاهز لاستقبال الطلبات |
| `GET /api/platform/setup-status` | نسبة اكتمال المتغيرات (يشمل `cameras`) |

---

## 3. إعداد Railway (مرة واحدة — بدون كود)

انسخ من [`.env.railway.example`](../.env.railway.example) إلى **Railway → Service web → Variables**.

### 3.1 حرجة (بدونها لا يعمل الإنتاج)

| المتغير | الوصف |
|---------|--------|
| `PUBLIC_BASE_URL` | رابط HTTPS للخدمة |
| `BAUPASS_SECRET_KEY` | ≥32 حرف عشوائي |
| `BAUPASS_AUDIT_SIGNING_KEY` | توقيع audit |
| `BAUPASS_DB_PATH=/data/baupass.db` | **Volume** على `/data` إلزامي |
| `BAUPASS_BACKUP_ON_BOOT=1` | نسخ احتياطي تلقائي |

### 3.2 موصى بها (Enterprise كامل)

| المتغير | الوصف |
|---------|--------|
| `REDIS_URL` | Redis من Railway |
| `BAUPASS_DAILY_JOBS_MODE=rq` | مهام يومية (PDF، كameras، FCM) |
| `BAUPASS_DUNNING_MODE=rq` | Mahnwesen |
| **Worker service** | أمر: `python -m backend.app.tasks.worker` |
| `SMTP_*` | بريد (تقارير، فواتير، **تنبيهات الكameras**) |
| `FCM_PROJECT_ID` + `FCM_SERVICE_ACCOUNT_JSON` | Push تطبيق العامل |
| `OPENAI_API_KEY` | KI / Copilot |
| `SENTRY_DSN` | مراقبة أخطاء |

### 3.3 الكameras (Baustelle)

| المتغير | الافتراضي | الوصف |
|---------|-----------|--------|
| `BAUPASS_RTSP_BRIDGE_TOKEN` | — | **إلزامي** للوكيل المحلي |
| `BAUPASS_CAMERA_HEALTH_SECONDS` | `120` | فحص offline |
| `BAUPASS_CAMERA_ONLINE_THRESHOLD_SECONDS` | `180` | حد «متصل» |
| `BAUPASS_CAMERA_NIGHTLY_DIGEST` | `1` | تقرير ليلي PDF |
| `BAUPASS_CAMERA_DIGEST_HOURS` | `12` | نافذة التقرير |

**لا تضع في الإنتاج:** `BAUPASS_ALLOW_DEMO=1` · `BAUPASS_SEED_DEMO_ENTERPRISE=1`

تفاصيل: [`docs/camera-rtsp-bridge-DE.md`](camera-rtsp-bridge-DE.md) · [`docs/enterprise-go-live-AR.md`](enterprise-go-live-AR.md)

---

## 4. النشر (بدون لمس الكود)

| الطريقة | متى |
|---------|-----|
| **GitHub Actions** `railway-deploy` | Push على `main` → نشر تلقائي |
| `.\deploy\railway-up.ps1` | نشر يدوي من CLI |
| `.\deploy\railway-cli-status.ps1` | حالة + logs + health |

بعد النشر: Migrations تُطبَّق تلقائياً عند الإقلاع (`site_cameras` وجداول الكameras included).

---

## 5. التشغيل اليومي (100% من الواجهة)

### 5.1 لوحات التحكم

| الواجهة | الرابط | من يستخدمها |
|---------|--------|-------------|
| WorkPass | `/index.html` | Superadmin، Company-admin |
| Betrieb / Admin v2 | `/admin-v2/index.html` | مدير الشركة، Ops |
| Worker PWA | `/emp-app.html` | العامل |
| Porter / Gate | من WorkPass | البوابة |

### 5.2 ما يمكن إدارته بدون كود

- شركات، خطط، فواتير، Mahnung
- عمال، badges، QR، NFC، Wallet
- أجهزة Drehkreuz (OSDP/TCP)
- **كameras:** تسجيل، live snapshot، أحداث أمنية
- Posteingang، Dokumente، DATEV
- Urlaub، Schichten، Einsatzplan
- KI Copilot (Enterprise)
- Automation rules

---

## 6. الكameras — التشغيل الكامل بدون كود

### 6.1 على السحابة (Railway) — مرة واحدة

1. عيّن `BAUPASS_RTSP_BRIDGE_TOKEN` (قيمة سرية طويلة)
2. تأكد من `SMTP_*` (لتقارير PDF والتنبيهات)
3. Deploy أحدث `main`

### 6.2 على موقع البناء — وكيل محلي

جهاز Windows/Linux/Mini-PC بجانب NVR:

```powershell
set BAUPASS_API_URL=https://baupass-production.up.railway.app
set BAUPASS_RTSP_BRIDGE_TOKEN=<نفس قيمة Railway>
set BAUPASS_COMPANY_ID=cmp-xxxxxxxx
set BAUPASS_CAMERA_ID=cam-gate-north
set BAUPASS_CAMERA_RTSP_URL=rtsp://user:pass@192.168.1.50/stream1
python scripts/rtsp_camera_agent.py --interval 60 --snapshot
```

**Heartbeat فقط (بدون حدث AI):**

```powershell
python scripts/rtsp_camera_agent.py --once --heartbeat --snapshot
```

### 6.3 من WorkPass → Geräte

1. **Kamera registrieren** (اسم + موقع)
2. شاهد **Online/Offline**
3. **Live-Snapshot** (آخر صورة كل 10 ثوانٍ)
4. **Sicherheitsereignisse** (PSA، منطقة محظورة، …)

### 6.4 ما يحدث تلقائياً (بدون تدخل)

| الحدث | رد الفعل |
|-------|----------|
| مخالفة (PSA، zone، …) | Alert + Inbox + **Email + PDF** للمسؤول |
| كamera offline > 3 د | Email + Alert |
| كل 24 س | **تقرير ليلي PDF** (آخر 12 س + offline) |

---

## 7. تطبيق العامل (Flutter / PWA)

| الخطوة | أين |
|--------|-----|
| APK / TestFlight | Railway: `BAUPASS_WORKER_APK_URL` · `BAUPASS_TESTFLIGHT_URL` |
| FCM Push | `FCM_PROJECT_ID` + Service Account |
| Checklist | `GET /api/worker-app/mobile-setup` |
| Docs | [`mobile/docs/firebase-push-setup.md`](../mobile/docs/firebase-push-setup.md) |

---

## 8. النسخ الاحتياطي والاستعادة

```powershell
python backend/ops/db_backup.py backup
python backend/ops/db_backup.py verify-restore
.\scripts\run_backup.ps1
.\scripts\verify_backup_restore.ps1
```

Runbook: [`docs/enterprise-backup-restore-runbook.md`](enterprise-backup-restore-runbook.md)

---

## 9. قائمة تحقق التسليم النهائية

### البنية التحتية

- [ ] Volume `/data` مُركّب على Railway
- [ ] `handover-ready.ps1` → exit 0
- [ ] `setup-status` ≥ 80%
- [ ] Redis + Worker service يعملان
- [ ] SMTP يُرسل (اختبار من WorkPass أو invoice test)

### البيانات

- [ ] شركة حقيقية + company-admin
- [ ] ≥1 Geofence بإحداثيات حقيقية
- [ ] ≥1 Worker + badge + QR tested
- [ ] **لا** demo seed في الإنتاج

### الكameras (إن وُجدت)

- [ ] `BAUPASS_RTSP_BRIDGE_TOKEN` مضبوط
- [ ] كamera مسجّلة في UI
- [ ] Agent يعمل على الموقع (`--interval 60 --snapshot`)
- [ ] Live-Snapshot يظهر في WorkPass
- [ ] اختبار مخالفة → email PDF (اختياري: `--event ppe_check` مع `ppe: false`)

### الجوال

- [ ] FCM configured · Push test OK
- [ ] APK / TestFlight link في join page

---

## 10. مرجع سريع — الأوامر

```powershell
# حالة Railway
.\deploy\railway-cli-status.ps1

# جاهزية التسليم الكاملة
.\deploy\handover-ready.ps1 -BaseUrl "https://YOUR_APP.up.railway.app"

# Health
.\deploy\railway-health-check.ps1 -BaseUrl "https://YOUR_APP.up.railway.app"

# اختبار ميداني
.\scripts\field-test.ps1

# وكيل كamera
python scripts/rtsp_camera_agent.py --interval 60 --snapshot
```

---

## 11. متى تحتاج مطوّراً؟

| الحالة | الحل بدون كود | يحتاج كود |
|--------|---------------|-----------|
| SMTP لا يعمل | تحقق Variables Brevo/Gmail | — |
| كamera offline | Agent + RTSP URL + شبكة | — |
| Push لا يصل | FCM JSON + Worker service | — |
| ميزة جديدة غير موجودة | — | نعم |
| Bug في API | Sentry + logs | نعم |

---

## 12. وثائق مرتبطة

| الموضوع | الملف |
|---------|-------|
| Go-Live Enterprise | [`enterprise-go-live-AR.md`](enterprise-go-live-AR.md) |
| Railway كامل | [`railway-production-setup-AR.md`](railway-production-setup-AR.md) |
| الكameras RTSP | [`camera-rtsp-bridge-DE.md`](camera-rtsp-bridge-DE.md) |
| PostgreSQL / DR | [`production-closure-100-AR.md`](production-closure-100-AR.md) |
| Backup | [`enterprise-backup-restore-runbook.md`](enterprise-backup-restore-runbook.md) |
| Enterprise checklist | [`ENTERPRISE-CHECKLIST-AR.md`](ENTERPRISE-CHECKLIST-AR.md) |
| حالة المنصة | [`STATUS-FULL-AR.md`](STATUS-FULL-AR.md) |

---

## 13. خلاصة التسليم

**WorkPass جاهزة للتشغيل المستقل:**

1. **Railway** يحمل المتغيرات + Volume + Redis + Worker  
2. **GitHub** ينشر تلقائياً — Migrations تلقائية  
3. **WorkPass / admin-v2** لإدارة كل شيء  
4. **RTSP Agent** على البaustelle للكameras  
5. **PDF + Email + Push** تلقائياً للتنبيهات  

**لا حاجة لفتح الكود** إلا لطلبات تطوير جديدة أو إصلاح عطل — التشغيل اليومي والتوسع (شركات، مواقع، كameras) كله من Variables والواجهة.

---

*للتحقق الآن:*

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\handover-ready.ps1
```
