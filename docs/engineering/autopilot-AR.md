# Autopilot — تقليل التدخل اليدوي

## الهدف

تشغيل المهام المتكررة **تلقائياً** مع إمكانية إيقاف كل بند من Admin v2 → تبويب **Plattform**.

## ما يعمل تلقائياً (افتراضياً مفعّل)

| الإعداد | السلوك |
|---------|--------|
| `autoAckInfoAlerts` | إغلاق تنبيهات النظام من نوع **info** الأقدم من 48 ساعة (للشركة) |
| `autoNotifyDocExpiry` | إشعار Push للموظف عن مستندات تنتهي خلال 14 يوماً (مرة واحدة / أسبوع / مستند) |
| `autoDailySecurityScan` | فحص أمني يومي + حدث `autopilot.daily` لقواعد الأتمتة |
| `autoSeedAutomationRules` | إنشاء قواعد أتمتة افتراضية عند أول تشغيل |
| `autoEnsureScheduledReport` | إنشاء job تقرير PDF يومي 08:00 إن لم يوجد وكان هناك بريد مدير |
| `autoInboxBulkDocPush` | دفع Push لكل عناصر «مستند ينتهي» في صندوق الوارد |
| `autoInboxAckLowSecurity` | إغلاق تنبيهات أمن `low` الأقدم من 7 أيام (اختياري، معطّل افتراضياً) |

## الجدولة

- يُستدعى `run_autopilot_cycle()` ضمن **دورة المهام اليومية** (`run_daily_jobs_cycle_once`).
- التقارير PDF تبقى على **مجدول كل دقائق** (`run_scheduled_ops_pdf_reports`) حسب المنطقة الزمنية.

## API

- `GET /api/platform/autopilot/settings?company_id=`
- `PATCH /api/platform/autopilot/settings` — `{ "settings": { "autoNotifyDocExpiry": false } }`
- `POST /api/platform/autopilot/run` — تشغيل فوري (شركة واحدة أو الكل لـ superadmin)

| `autoPrepareNextMonthDeployment` | من اليوم 20: مسودة الشهر القادم من نمط أيام الأسبوع |
| `autoSendDeploymentPlans` | **دائماً معطّل** — لا إرسال Einsatzplan دون تأكيد المستخدم |

## ما لا يُؤتمت افتراضياً (قرارات حساسة)

- الموافقة على الإجازات
- رفض/قبول فواتير يدوياً
- قفل موظف دون سياسة صريحة

يمكن لاحقاً إضافة سياسات اختيارية (مثلاً إجازة يوم واحد) خلف toggle معطّل افتراضياً.

## ما يعمل مسبقاً في المنصة (بدون Autopilot)

- فواتير شهرية، إعادة محاولة الإرسال، dunning
- قفل موظفين بمستندات منتهية
- تنبيهات انتهاء المستندات بالبريد و FCM
- نسخ احتياطي SQLite يومي
- محرك قواعد الأتمتة عند الأحداث (`events/bus` → `evaluate_event`)
