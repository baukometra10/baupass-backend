# حزمة الأمن المؤسسي — WorkPass

هذه المجلدات والوثائق تهدف إلى **زيادة الثقة** عند التفاوض مع المؤسسات الكبرى والجهات الحكومية. المحتوى يُحدَّث تدريجياً؛ بعض البنود **إجرائية** (خارج الكود) ويجب إكمالها مع فريق الأمن القانوني.

| الوثيقة | الغرض |
|---------|--------|
| [threat-model-AR.md](./threat-model-AR.md) | نموذج التهديدات (STRIDE مبسّط) |
| [incident-response-AR.md](./incident-response-AR.md) | خطة الاستجابة للحوادث |
| [disaster-recovery-AR.md](./disaster-recovery-AR.md) | التعافي من الكوارث والنسخ الاحتياطي |
| [data-classification-AR.md](./data-classification-AR.md) | تصنيف البيانات والاحتفاظ |
| [sso-roadmap-AR.md](./sso-roadmap-AR.md) | SAML 2.0, OIDC, Entra, Keycloak, AD |
| [security-architecture-AR.md](./security-architecture-AR.md) | طبقات الأمن ومخطط الثقة |
| [iso27001-readiness-AR.md](./iso27001-readiness-AR.md) | خريطة ضوابط ISO 27001 |
| [penetration-testing-AR.md](./penetration-testing-AR.md) | اختبار الاختراق — نطاق وتكرار |
| [business-continuity-AR.md](./business-continuity-AR.md) | استمرارية الأعمال (BCP) |

## ما هو موجود في المنصة اليوم

- مصادقة جلسات + 2FA اختياري
- RBAC (`superadmin`, `company-admin`, `turnstile`, …)
- سجلات تدقيق (access logs, automation, تقارير)
- SSO: Microsoft Entra + Google (OIDC)
- عزل مستأجرين (Multi-Tenant)
- PostgreSQL + نسخ احتياطي (انظر `docs/enterprise-backup-restore-runbook.md`)
- Zero-trust middleware (طبقة platform)

## ما يُنفَّذ خارج الكود (موصى به)

- **اختبار اختراق** سنوي (أو قبل كل عقد حكومي كبير)
- **تدقيق ISO 27001** عند الطلب
- **تكامل SIEM** (تصدير السجلات إلى Splunk / Sentinel / ELK)
- **اتفاقية معالجة بيانات (DPA)** وملحق أمن

## جهات الاتصال (يُملأ من العميل)

| الدور | الاسم | البريد |
|-------|-------|--------|
| مسؤول أمن المعلومات | _TBD_ | _TBD_ |
| مسؤول الامتثال | _TBD_ | _TBD_ |
| جهة اتصال طوارئ 24/7 | _TBD_ | _TBD_ |
