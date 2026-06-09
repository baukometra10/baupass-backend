# أجهزة التوقيع — دليل شامل (أي ماركة)

BauPass **لا يفرض** ماركة واحدة. زر **«جهاز التوقيع»** يكتشف تلقائياً أي جسر محلي مثبت.

## الماركات المدعومة

| الماركة | البرنامج على PC المكتب | ملفات اختيارية |
|--------|------------------------|----------------|
| **Signotec** | signoPAD-API/Web (port 49494) | `vendor/signotec/STPadServerLib.js` |
| **Wacom STU** | Wacom STU SigCaptX | `vendor/wacom/q.js` + `wgssStuSdk.js` |
| **StepOver** | Pad Connector | — (WebSocket مباشر) |
| **Topaz** | SigWeb | `vendor/topaz/SigWebTablet.js` |
| **أي USB** | — | التوقيع على اللوحة البيضاء |

## ترتيب الاكتشاف التلقائي

1. Signotec → 2. Wacom → 3. StepOver → 4. Topaz → 5. اللوحة على الشاشة

## Signotec

1. [signoPAD-API/Web](https://en.signotec.com/portal/seiten/download-developer-tools-api-sdk--900000510-10002.html)
2. نسخ `STPadServerLib.js` → `vendor/signotec/`
3. تشغيل STPadServer

التوقيع يظهر على **شاشة الجهاز** مع نص مخصص.

## Wacom (STU-430, 530, 540, 640…)

1. [Wacom STU SigCaptX](https://developer-docs.wacom.com/docs/stu-sdk/windows-sdk/sigcaptx/sigcaptx-getting-started/)
2. نسخ `q.js` و `wgssStuSdk.js` من [samples/demobuttons](https://github.com/Wacom-Developer/stu-sdk-sigcaptx-samples/tree/master/samples/demobuttons) → `vendor/wacom/`
3. التحقق: افتح `PortCheck.html` من عينات Wacom

يظهر مربع توقيع على شاشة الجهاز مع أزرار OK / Clear / Cancel.

## StepOver (naturaSign, duraSign…)

1. [Pad Connector](https://stepover.com/en/products/developer/pad-connector/) — مجاني (Standard)
2. تأكد من الاتصال: `https://signsocket.stepover.com:57357`
3. لا حاجة لنسخ ملفات JS

## Topaz (SigLite, SigGem…)

1. [SigWeb SDK](https://www.topazsystems.com/sdks/sigweb.html)
2. نسخ `SigWebTablet.js` → `vendor/topaz/`
3. في Chrome/Edge 142+: Allow **Local Network Access**

## أي جهاز USB بدون برنامج

استخدم **اللوحة البيضاء** في نموذج Mitarbeiter — القلم يرسم مباشرة.

## Desktop-Agent (اختياري)

`POST /api/device/signature/capture` — راجع `docs/device-signature-bridge-DE.md`

## استكشاف الأخطاء

| المشكلة | الحل |
|---------|------|
| لا يلتقط من الجهاز | البرنامج يجب أن يعمل على **نفس PC** الذي يفتح المتصفح |
| Signotec lib missing | انسخ `STPadServerLib.js` |
| Wacom service not ready | ثبّت SigCaptX وأعد تشغيل PC |
| StepOver unreachable | ثبّت Pad Connector وافتح `signsocket.stepover.com:57357` |
| Topaz not installed | ثبّت SigWeb |
| LCD لا يظهر «وقّع هنا» | USB وحده لا يكفي — تحتاج جسر الماركة |
