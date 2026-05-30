# خارطة طريق BauPass المؤسسية 2026

> **مبدأ التوجيه:** النضج والاستقرار والامتثال وقابلية التدقيق — **قبل** مزايا جديدة كثيرة (Marketplace، AI تجريبي، إلخ).  
> **النواة:** الهوية الرقمية + الدخول + العمال + الامتثال + المستندات + التقارير + الفوترة.

---

## الحالة الحالية (ما بدأناه)

| # | المحور | الحالة | مرجع |
|---|--------|--------|------|
| 1 | تفكيك `server.py` | 🟡 **9 مسارات reporting** في domain blueprint | `engineering/server-decomposition-roadmap.md` |
| 2 | SSO مؤسسي | 🟡 Entra + groups→roles، Keycloak، SAML scaffold، `/api/auth/sso/catalog` | `enterprise-security/sso-roadmap-AR.md` |
| 3 | حزمة أمن | 🟡 + Security Architecture | `enterprise-security/` |
| 4 | ISO 27001 | 🟡 خريطة ضوابط | `enterprise-security/iso27001-readiness-AR.md` |
| 5 | متعدد القطاعات | ✅ 7 قطاعات incl. aviation | `product-repositioning-AR.md` |
| 6 | UX | 📋 ميثاق | `engineering/ux-maturity-charter-AR.md` |
| 7 | تقارير PDF | 🟡 **Executive PDF** + scheduled jobs API | `engineering/reporting-roadmap-AR.md` |
| 8 | RBAC موسّع | 🟡 **فرض auditor read-only** + تعيين أدوار API | `engineering/rbac-enterprise-model-AR.md` |
| 9 | أرشفة / Retention | 🟡 **API retention + legal hold + export** | `governance/retention-and-archive-AR.md` |
| 10 | مراقبة / SLA | 🟡 SIEM CEF + verify chain | `operations/sla-monitoring-AR.md` |
| 11 | وثائق نظام | 🟡 توسيع مستمر | `architecture/README.md` |
| 12 | On-Prem / حكومي | 🟡 **Helm values-government** + air-gap playbook | `deploy/air-gapped-playbook-AR.md` |
| 13 | Audit trail | 🟡 immutable chain + **verify API** | `governance/audit-trail-immutable-AR.md` |
| 14 | Data governance | 📋 | `governance/data-governance-AR.md` |
| 15 | تكاملات SAP/Oracle/M365/DATEV | 🟡 DATEV نشط — نضج الباقي | `integrations/enterprise-integrations-AR.md` |
| 16 | عدم التشتيت | ✅ ميثاق أولويات | `engineering/stability-charter-AR.md` |
| 17 | لا مزايا تجريبية كبيرة الآن | ✅ | هذا المستند |
| 18 | إزالة MVP/Prototype | 🟡 جارٍ في الواجهة و README | — |
| 19 | Enterprise / Government Edition | 📋 تعريف إصدار | `editions/enterprise-government-edition-AR.md` |
| 20 | نضج تشغيلي | ✅ أولوية فريق | `engineering/stability-charter-AR.md` |

---

## المراحل الزمنية المقترحة

### المرحلة A — استقرار (8–12 أسبوعاً)

- إكمال نقل **auth → access → billing** من `server.py` إلى domains
- اختبارات CI لكل domain منقول
- إصلاح حواف SSO (Redis state، رسائل خطأ واضحة)
- إكمال SAML ACS (python3-saml أو authlib)
- Pentest خارجي واحد + معالجة P1/P2

### المرحلة B — امتثال وبيع مؤسسي (3–6 أشهر)

- ISO 27001 readiness pack (سياسات + أدلة)
- RBAC enforced + group mapping من Entra
- تقارير تنفيذية PDF موحّدة + جدولة
- Retention + legal hold (schema + API)

### المرحلة C — حكومي / سيادي (عند الطلب)

- On-prem Helm hardened
- Air-gapped playbook
- SIEM export (CEF/JSON)
- Immutable audit store (WORM / append-only)

---

## ما لن نفعله الآن (صريح)

- Marketplace / متجر إضافات
- موجات AI جديدة قبل استقرار التشغيل
- تكاملات «عرضية» بدون عميل ملزم

---

## روابط سريعة

- [إعادة التموضع](./product-repositioning-AR.md)
- [رؤية المنصة](./platform-vision-AR.md)
- [تفكيك server.py](./engineering/server-decomposition-roadmap.md)
- [أمن مؤسسي](./enterprise-security/README.md)
