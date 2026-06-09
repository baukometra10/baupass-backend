# Signotec — إعداد جهاز التوقيع مع BauPass

جهاز **signotec GmbH** (Sigma, Zeta, Omega, Gamma, Delta, Alpha…) يعمل مع BauPass عبر **signoPAD-API/Web** — برنامج وسيط على كمبيوتر المكتب يتصل بالـ USB ويفتح WebSocket للمتصفح.

## لماذا لم يظهر «وقّع هنا» على الجهاز؟

توصيل USB **لا يكفي**. المتصفح لا يتحدث مع USB مباشرة. تحتاج:

1. **تثبيت signoPAD-API/Web** على نفس PC الذي يفتح فيه Control Pass  
2. **تشغيل STPadServer** (خدمة Windows أو يدوياً)  
3. **نسخ `STPadServerLib.js`** إلى `vendor/signotec/` في المشروع (أو على السيرver static files)  
4. في BauPass: **Mitarbeiter** → زر **«جهاز التوقيع»** (يكتشف Signotec تلقائياً)

راجع أيضاً: [signature-pad-setup-AR.md](./signature-pad-setup-AR.md) للماركات الأخرى (Topaz، USB بدون برنامج).

## خطوات التثبيت

### 1) تحميل وتثبيت

- [Developer Tools / signoPAD-API/Web](https://en.signotec.com/portal/seiten/download-developer-tools-api-sdk--900000510-10002.html)
- ثبّت **signoPAD-API/Web** + **Pad driver** من نفس الحزمة
- أعد تشغيل PC بعد التثبيت

### 2) التحقق من الخادم المحلي

افتح PowerShell:

```powershell
Get-Process STPadServer -ErrorAction SilentlyContinue
```

إن لم يعمل:

```powershell
& "C:\Program Files\signotec\signoPAD-API Web\STPadServer.exe" 49494
```

المنفذ الافتراضي: **49494** (`wss://local.signotecwebsocket.de:49494`)

### 3) مكتبة JavaScript

انسخ من مجلد التثبيت:

```
STPadServerLib.js  →  vendor/signotec/STPadServerLib.js
```

### 4) استخدام BauPass

1. سجّل الدخول إلى Control Pass على **نفس PC**  
2. **Mitarbeiter** → أنشئ أو عدّل موظفاً  
3. في قسم **Unterschrift bei Ausweisübergabe** اضغط **Signotec Pad**  
4. على **شاشة جهاز Signotec** يظهر النص — يوقّع الموظف ويضغط **Confirm** على الجهاز  
5. التوقيع يُنسخ تلقائياً إلى النموذج → **Speichern**

## استكشاف الأخطاء

| الم symptom | الحل |
|------------|------|
| «signoPAD-API/Web nicht gefunden» | ثبّت Web + انسخ `STPadServerLib.js` |
| WebSocket timeout | شغّل STPadServer، تحقق من الجدار الناري |
| الجهاز لا يُكتشف | إعادة توصيل USB، تحديث driver من signotec |
| يعمل على Railway لكن ليس محلياً | التوقيع **محلي فقط** — المتصفح على PC المكتب وليس السحابة فقط |

## API بديل (بدون WebSocket)

لأتمتة من برنامج خارجي:

`POST /api/device/signature/capture`  
Header: `X-BauPass-Signature-Token` = `BAUPASS_SIGNATURE_BRIDGE_TOKEN`

راجع: [device-signature-bridge-DE.md](./device-signature-bridge-DE.md)

## ترخيص

signoPAD-API/Web مجاني لـ **≤50 جهاز**. أكثر من ذلك: اتفاق مع signotec GmbH.
