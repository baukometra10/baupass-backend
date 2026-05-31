# اختبار الاختراق (Penetration Testing) — BauPass

## الهدف

تأكيد أن سطح الهجوم (ويب، API، تطبيق العامل، Webhooks) يتماشى مع **Threat Model** (`threat-model-AR.md`) قبل عقود Enterprise/Government.

## النطاق الموصى به

| طبقة | أمثلة |
|------|--------|
| API | `/api/login`, SSO callbacks, `/api/worker/*`, rate limits |
| Admin | `index.html`, `admin-v2`, superadmin preview |
| Worker PWA | `emp-app.html`, JWT/session |
| بنية | Tenant isolation, IDOR على `company_id` |
| تكاملات | Webhooks, RTSP bridge, push tokens |

## التكرار

- **سنوي** كامل للإنتاج
- **عند إصدار major** أو تغيير SSO/ RBAC
- **بعد Pentest** — معالجة P1 خلال 7 أيام، P2 خلال 30 يوماً

## مخرجات مطلوبة

1. تقرير تنفيذي (عربي/ألماني)
2. قائمة CVE/ findings مع CVSS
3. إعادة اختبار (retest) بعد الإصلاح
4. تحديث `threat-model-AR.md` إن ظهرت تهديدات جديدة

## علاقة ISO 27001

يربط بضوابط A.8 (أمن التطبيقات) و A.5 (سياسات) — راجع `iso27001-readiness-AR.md`.

## أدوات مرجعية (خارجية)

OWASP ZAP, Burp Suite Pro, nmap (محدود), dependency scan (`pip audit`, npm audit في CI).
