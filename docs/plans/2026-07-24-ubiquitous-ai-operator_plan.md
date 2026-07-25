## 0) حالة التنفيذ — مكتمل (+ تقدّم 2026-07-25)

- **2026-07-24:** المرحلة A منفّذة (FAB + درج محادثة + تأكيد + تنقّل admin-v2).
- **2026-07-24:** المرحلة B منفّذة: Einsatzplan + تذكيرات + security/system + broadcast تحت propose→approve.
- **2026-07-24:** حقن مركزي لكل صفحات HTML عبر `ai_operator_inject.py`.
- **2026-07-24:** Voice في الدرج (Mic + TTS + Hands-free).
- **2026-07-24:** شريط أيقونات + محادثة جديدة + جلسة + مصادر.
- **2026-07-24:** مهام حتمية موسّعة (Tageslage، موظف، حضور، Forecast، Outside-Hours، Risk، Timeline، Fraud، تنقّل).
- **2026-07-24:** صوت وواجهة على كل لغات النظام الثماني (`de/en/ar/tr/fr/es/it/pl`).
- **2026-07-24:** **المرحلة E مكتملة:** تحية صوتية عند فتح النظام للأدمن — افتراضياً `BAUPASS_AI_OPERATOR_WELCOME=1`؛ اختصارات lokalized؛ تسميات أزرار بـ 8 لغات؛ `operator_i18n.py`.
- **2026-07-24:** **Ambient voice:** بعد التحية يستمع فوراً بدون ضغط FAB؛ عند الكلام يفتح الدرج ويعرض النص؛ الكتابة الحساسة → بطاقة + سؤال صوتي «هل أنفّذ؟»؛ إيقاف تلقائي عند الصمت (`autoStopOnSilence`).
- **2026-07-24:** كشف لغة تلقائي من Whisper + ملخص صباحي بعد التحية + نموذج أدمن أقوى (`gpt-4o` / `BAUPASS_AI_MODEL_ADMIN`) + UI Pilot allowlisted (نقر تبويبات/صفحات بأمان) + إيقاف الاستماع بزر FAB أثناء التسجيل.
- **2026-07-25:** ChatGPT-style dictation (صمت ~5ث → نص كامل → إرسال).
- **2026-07-25:** ElevenLabs auto عند وجود المفتاح (`BAUPASS_TTS_PROVIDER=auto`) + Voice IDs لـ 8 لغات عبر env.
- **2026-07-25:** تحية + briefing مرة واحدة بعد Login (ليس عند كل قسم).
- **2026-07-25:** رد بنفس لغة الكلام (Whisper language) في FAB / Command Center / Hub.
- **2026-07-25:** إيقاف شركة واحد يخفي FAB في كل الصفحات + gating باقة Enterprise (`ai_assistant`) + إعدادات voice/welcome لكل شركة.
- **2026-07-25:** Alt+A / Escape · barge-in (الميك يوقف TTS) · زر كتم الرد الصوتي · شارات جاهزية الصوت · chips حسب الصفحة · UI Pilot لـ Hub/Ops/AI Center.
- **2026-07-25:** Proaktiver Ops-Pulse (Security-Risiken → FAB urgent + Toast) · Live-Prompts vom Server · Recent-Prompts · mehrsprachige Operator-Intents (FR/ES/IT/TR).
- **2026-07-25:** `GET /api/ai/operator/pulse` mit priorisierten Empfehlungen · Intent „Was soll ich priorisieren?“ · Actions `export_ops_snapshot` + `resolve_inbox_item`.
- **2026-07-25:** Morgen-Pulse per Slack/Teams/E-Mail (Cron + `POST …/pulse/dispatch`) · Site-Copilot: Pulse/Chips nach Tab/Seite (contracts/docs/workers/…).
- **2026-07-25:** Briefing-Uhrzeiten **pro Firma** — Default **`auto`** (1h vor `work_start`/Schichtstarts; TZ aus Firmen-Report-TZ). Override manuell `6,14,22`.
- **2026-07-25:** Briefing-Empfänger **auto pro Firma** (`company-admin` → Billing/Firmen-Mail; globales `BAUPASS_AI_BRIEFING_EMAIL` nur Fallback).
- **2026-07-25:** Briefing-Sprache **auto pro Firma** (`invoice_email_lang` → de/en/ar/tr/fr/es/it/pl; Env nur Fallback).
- **2026-07-25:** Sektor-Formulierungen in Pulse/Briefing/FAB/Tasks · Operations-Preview (Empfänger/Lang/Stunden/Sektor) · Firmen-Memory · Audit `ai.action.*` · Stimme Ja/Nein (bestehend + gehärtet).
- **2026-07-25:** Pulse-Labels TR/FR/ES/IT/PL · Operations Audit-UI + Live-Status (TTS/Cron/SMTP) · FAB-Chip „gleiche Erinnerung“.

Flags:
- `BAUPASS_AI_OPERATOR_FAB` (افتراضي 1)
- `BAUPASS_AI_OPERATOR_VOICE` (افتراضي 1)
- `BAUPASS_AI_OPERATOR_WELCOME` (افتراضي 1 — عطّل بـ `0`)
- `BAUPASS_AI_MODEL_ADMIN` (افتراضي فعلي `gpt-4o` للأدمن)
- `BAUPASS_AI_SPOKEN_TOOLS_ADMIN` (افتراضي 1 — أدوات حتى في الوضع الصوتي)

---

## 1) القرار

مشغّل نظام عبر APIs + FAB + تأكيد قبل الكتابة — بدون RPA على DOM.

---

## 2) مراحل التنفيذ

| مرحلة | حالة |
|--------|------|
| A — FAB + Drawer + stream + تأكيد | ✅ |
| B — كتابة آمنة تحت التأكيد | ✅ |
| C — تنقّل بصري | ✅ |
| D — صوت داخل الدرج | ✅ |
| E — تحية صوتية + i18n ثماني كامل للواجهة/الصوت | ✅ |

---

## 3) معايير النجاح

- [x] زر AI بعد تسجيل الدخول
- [x] قراءة فورية عبر stream
- [x] كتابة → بطاقة تأكيد
- [x] مسار Einsatzplan
- [x] مسار بحث + إشعار
- [x] لا كسر لـ Command Center / Copilot
- [x] صوت إدخال/إخراج/Hands-free
- [x] تحية عند فتح النظام (أدمن)
- [x] لغات النظام الثماني للصوت والواجهة

---

## 4) خارج النطاق (مقصود)

- تنفيذ بدون أي تأكيد
- قفل/فتح عمال عبر الوكيل
- استبدال Command Center
- أتمتة متصفح Playwright عند العميل
