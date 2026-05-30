# خطة التوزيع اليومية (Einsatzplan) — PDF احترافي

## الفكرة

لكل موظف: جدول شهري يوضح **أين يعمل كل يوم** (مثلاً برلين شارع X، غداً ألكسندر بلاتز، بعد غد بوتسدام). المنصة تولّد **PDF منسّق** باسم الموظف، الشهر، السنة، رقم البطاقة، وشعار الشركة (نصي).

## الباقات (Plan)

| القدرة | الحد الأدنى | ماذا يفعل |
|--------|-------------|-----------|
| `scheduling` | Professional | حفظ الأيام، استيراد من Schichten، قالب تناوب |
| `deployment_plan` | Professional | PDF فردي + إرسال بريد/Push للموظف |
| `deployment_plan_bulk` | Enterprise | ZIP لكل الموظفين الذين لديهم مواقع |

Starter / Tageskarte: ترقية مطلوبة (رسالة `feature_not_available`).

## API

- `GET /api/workforce/deployment-plan?worker_id=&year=&month=&lang=de`
- `PUT /api/workforce/deployment-plan` — `{ workerId, year, month, days: [{ date, location, notes }] }`
- `POST /api/workforce/deployment-plan/from-shifts`
- `POST /api/workforce/deployment-plan/rotation` — `{ locations: ["Berlin", "Potsdam", ...], skipWeekends: true }`
- `POST /api/workforce/deployment-plan/pdf` — يرجع `application/pdf`
- `POST /api/workforce/deployment-plan/bulk-pdf` — ZIP (Enterprise)
- `POST /api/workforce/deployment-plan/distribute` — بريد + Push (موظف واحد — معاينة)
- `GET /api/workforce/deployment-month` — حالة الشهر + ملخص الموظفين
- `POST /api/workforce/deployment-month/prepare-next`
- `POST /api/workforce/deployment-month/confirm-send` — `{ confirmSend: true }` **مطلوب**
- `POST /api/workforce/deployment-month/reopen` — إعادة فتح للتعديل

## الواجهة

**Admin v2 → Mitarbeiter → Einsatzplan** — محرّر الشهر، أزرار: من الورديات، تناوب 3 مواقع، حفظ، PDF، إرسال.

## الجدول

`worker_deployment_days` — مفتاح فريد `(company_id, worker_id, work_date)`.

## دورة الشهر (حفظ + تأكيد + إرسال)

1. **حفظ** — كل تعديل يُخزَّن في `worker_deployment_days` (دائم في النظام).
2. **تحضير الشهر القادم** — يدوياً («Nächsten Monat vorbereiten») أو تلقائياً من Autopilot **ابتداءً اليوم 20** (نمط أيام الأسبوع من الشهر الحالي) → حالة **مسودة / بانتظار المراجعة**.
3. **تعديل** — في أي وقت عبر Einsatzplan لكل موظف؛ إذا كان الشهر «مُرسَلاً» يعود تلقائياً إلى **مسودة** عند التعديل.
4. **إرسال** — فقط عبر **«Versand bestätigen»** + خانة اختيار التأكيد → `POST .../confirm-send` مع `confirmSend: true`.
5. **لا إرسال تلقائي** — `autoSendDeploymentPlans` دائماً `false` في Autopilot.

جدول الحالة: `deployment_month_batches` — `draft` | `sent` + `awaiting_confirm`.

## Autopilot (صندوق الوارد)

في **Plattform → Autopilot**:

- **Push تلقائي لمستندات صندوق الوارد** (مع تنبيهات المستندات)
- **إغلاق تنبيهات أمن low القديمة** (اختياري، معطّل افتراضياً)
