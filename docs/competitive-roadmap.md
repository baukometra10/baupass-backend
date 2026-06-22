# WorkPass / ControlPass – Wettbewerbs- & Sicherheits-Roadmap

## تم تنفيذه الآن (Mai 2026, Build `20260524j`)

### توقيع تسليم الهوية (بدون توقيع في تطبيق الموظف)

- **لا يوقّع الموظف على هاتفه** عند استلام البطاقة أو فتح الـ PWA.
- التوقيع يُلتقط **في لوحة الإدارة فقط** (لوح أو تابلت المكتب) ضمن نموذج المستخدم.
- يُخزَّن كـ PNG في قاعدة البيانات: `compliance_signature_data` مع وقت التسجيل والمستخدم الذي سجّله.
- حقل اختياري: **تاريخ تسليم الهوية** (`id_handover_at`).
- API:
  - `GET/PUT /api/workers/<id>/compliance-signature`
  - حقول اختيارية في `POST/PUT /api/workers`
- العرض في **تفاصيل الموظف** و**ملف المستخدم (Mitarbeiterakte)**.

### تحسينات إضافية (نفس الإصدار)

| الميزة | الوصف |
|--------|--------|
| **لوحة Einsatzlage** | `GET /api/operations/snapshot` + بطاقات على Dashboard |
| **نسخ SQLite** | يومي تلقائي + `POST /api/admin/database/backup` + `deploy/backup-db.ps1` |
| **PDF Akte** | `GET /api/workers/{id}/akte.pdf` (بيانات + توقيع) |
| **2FA Superadmin** | إلزامي عند تسجيل الدخول (`BAUPASS_REQUIRE_SUPERADMIN_2FA`) + تنبيه في Dashboard |
| **HSTS** | تلقائي عند `PUBLIC_BASE_URL` = HTTPS |
| **Audit غير قابل للتلاعب** | مرآة لأحداث الأمان (`BAUPASS_IMMUTABLE_AUDIT`) |
| **فهارس DB** | Migration `011` |
| **Railway env** | `.env.railway.example` |

---

## المرحلة 1 – استقرار الإنتاج (أسبوع 1–2)

| الأولوية | الموضوع | الفائدة |
|----------|---------|---------|
| P0 | Railway: `PUBLIC_BASE_URL`, Volume `/data`, SMTP/Brevo | بريد OTP وروابط صحيحة |
| P0 | Cache bust بعد كل نشر (`?v=BUILD`) | لا واجهة قديمة |
| P1 | نسخ احتياطي يومي SQLite → S3/Blob | استعادة بعد عطل |
| P1 | مراقبة `/api/health` + تنبيه Uptime | كشف توقف الخدمة |

---

## المرحلة 2 – أمان وتنافسية (أسبوع 3–6)

| الأولوية | الموضوع | الفائدة |
|----------|---------|---------|
| P0 | Redis لحد المعدّل (تسجيل دخول، OTP) | حماية من الهجمات |
| P0 | 2FA لـ Superadmin (TOTP موجود – تفعيل إلزامي) | حماية الحسابات الحساسة |
| P1 | Audit trail غير قابل للتلاعب (`immutable_audit`) في الإنتاج | امتثال GDPR/بناء |
| P1 | فصل `server.py` إلى وحدات (workers, billing, gate) | سرعة التطوير وأقل أخطاء |
| P2 | CSP + HSTS صارم على Railway | أمان المتصفح |
| P2 | تشفير at-rest لحقول حساسة (SMTP, مفاتيح) | امتثال |

---

## المرحلة 3 – منتج وسرعة (شهر 2–3)

| الأولوية | الموضوع | الفائدة |
|----------|---------|---------|
| P0 | Apple/Google Wallet للبطاقة | ميزة تنافسية قوية في السوق |
| P1 | NFC / HCE في الموقع (موجود جزئياً – اختبار ميداني) | دخول بدون تلامس |
| P1 | تنبيهات انتهاء المستندات (بريد + لوحة) | تقليل مخاطر الموقع |
| P1 | فهرسة SQLite على `workers.badge_id_lookup`, `access_logs.timestamp` | قوائم أسرع مع آلاف السجلات |
| P2 | CDN للأصول الثابتة | تحميل أسرع عالمياً |
| P2 | تصدير PDF للعقد + التوقيع في **ملف واحد** | أرشيف قانوني جاهز |

---

## المرحلة 4 – إيرادات وSaaS (شهر 3+)

- فواتير + Mahnung آلية (موجود – تحسين UX ولوحة مؤشرات).
- خطط Pro/Enterprise مع حدود واضحة (موظفين، مواقع، Wallet).
- API عامة للشركاء (Pförtner، Zeiterfassung).
- White-label كامل (شعار، ألوان، نطاق فرعي) – جزء منه موجود.

---

## توصيات فورية للمنافسة

1. **توقيع الإدارة + تاريخ التسليم** – تم (لا تعتمد على هاتف العامل).
2. **Wallet خلال 4–6 أسابيع** – أكبر فرق أمام حلول البطاقة البلاستيكية فقط.
3. **استقرار Railway + نسخ احتياطي** – بدونها لا تُباع الثقة للعملاء.
4. **صفحة تثبيت PWA واحدة** مع رابط شركة – تقليل دعم الهاتف.
5. **لوحة مؤشرات للإدارة**: من على الموقع الآن، مستندات منتهية، زيارات متأخرة.

---

## Build-Tag

Admin-UI nach Deploy: `?v=20260524l` (Service Worker v78).

### Dashboard & Admin (Build `20260524l`)

- Dashboard: **Bald ablaufende Dokumente** (Top-Liste, Link zu Dokumente)
- Admin: **Wallet & Mitarbeiter-App** (Apple/Google/SMTP/Redis/Backups + Install-Link kopieren)
- Systemstatus: Runtime-Warnungen aus `get_runtime_diagnostics()`
