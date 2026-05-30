# إعادة تموضع BauPass — منصة الهوية المؤسسية والتحكم التشغيلي

## 1. الرسالة الجديدة

**BauPass** ليست «منصة بناء فقط». المنتج الأساسي هو:

- **الهوية الرقمية** للأفراد والزوار والمقاولين الفرعيين.
- **التحكم بالدخول** (بوابات، NFC، جغرافيا، Turnstile).
- **إدارة القوى العاملة** والمستندات والامتثال.
- **التقارير والتدقيق** والفوترة متعددة المستأجرين.

قطاع **البناء** يبقى نقطة انطلاق قوية، لكن المصطلحات والقوالب التشغيلية تُخصَّص حسب القطاع.

---

## 2. ما تم تنفيذه (أساس تقني)

| العنصر | المسار / API |
|--------|----------------|
| قطاعات تشغيل | `construction`, `manufacturing`, `logistics`, `security`, `public_sector`, `government` |
| عمود قاعدة البيانات | `companies.operating_sector` (افتراضي: `construction`) |
| كتالوج المصطلحات | `backend/app/platform/sector/catalog.py` |
| API القطاعات | `GET /api/platform/sectors` |
| إعدادات المستأجر | `GET /api/platform/sector-config` (يتطلب جلسة) |
| واجهة الإدارة | `#companyOperatingSector` + `loadSectorTerminology()` + `uiT()` |
| كتالوج أدوار مؤسسية | `GET /api/platform/rbac/catalog` (`planned` / `active`) |
| SSO | Entra OIDC + Google (نشط) — SAML/Keycloak مخطَّط (انظر `enterprise-security/sso-roadmap-AR.md`) |

---

## 3. أولويات الفترة القادمة (استقرار قبل التوسع)

1. **اختبارات** — توسيع `backend/tests/` (قطاع، RBAC، تقارير، SSO smoke).
2. **أداء** — استعلامات ثقيلة في `server.py`، تخزين مؤقت للوحة.
3. **حواف برمجية** — جلسات منتهية، مستأجرون بدون `operating_sector`، معاينة السوبرأدمن.
4. **أمان** — مراجعة `require_roles`، rate limits، تدوير مفاتيح API.
5. **تفكيك `server.py`** — انظر `engineering/server-decomposition-roadmap.md`.

**لا نضيف عشرات المزايا الجديدة** قبل استقرار ما هو موجود.

---

## 4. خارطة طريق المنتج (مختصرة)

| المحور | الحالة |
|--------|--------|
| مصطلحات حسب القطاع | ✅ أساس (API + UI) |
| قوالب تشغيل لكل قطاع | 🟡 metadata في `OPERATION_TEMPLATES` — ربط بالواجهة لاحقاً |
| أدوار مؤسسية دقيقة | 🟡 كتالوج فقط — فرض الصلاحيات لاحقاً |
| تقارير + تدقيق + تصدير | ✅ قوي — يبقى أولوية |
| حزمة أمن مؤسسية | 🟡 وثائق في `docs/enterprise-security/` |
| ISO 27001 / SIEM / retention | 📋 تحضير مبكر (وثائق + سياسات) |
| تجربة Enterprise UX | تبسيط الشاشات، توحيد التصميم، موبايل/تابلت |

---

## 5. نقطة القوة التي نحافظ عليها

الذكاء الاصطناعي والطبقات الست مكمّلات — **النواة** هي الجمع بين:

الهوية + الدخول + العمال + الامتثال + المستندات + التقارير + الفوترة.

أي ميزة جديدة يجب أن تقوّي هذا المحور، لا أن تشتت الواجهة.

---

## 6. مراجع

- [`docs/enterprise-roadmap-2026-AR.md`](./enterprise-roadmap-2026-AR.md) — الخطة الشاملة (20 بنداً)
- `docs/platform-vision-AR.md`
- `docs/engineering/stability-charter-AR.md`
- `docs/engineering/server-decomposition-roadmap.md`
- `docs/enterprise-security/README.md`
