# خارطة طريق BauPass المؤسسية 2026 — 30 بنداً

> **مبدأ التوجيه:** النضج والاستقرار والامتثال وقابلية التدقيق — قبل مزايا تجريبية كثيرة.  
> **النواة (بند 29):** الهوية الرقمية · الدخول · الامتثال · المستندات · التقارير · الفوترة.

**آخر تحديث تنفيذ:** 2026-05-30

---

## جدول البنود والحالة

| # | المحور | الحالة | مرجع / ملاحظة |
|---|--------|--------|----------------|
| 1 | تفكيك `server.py` → Domains | 🟡 | reporting 9؛ **auth** + `login_flow.py`؛ **access**: logs + gates/tap |
| 2 | SSO (SAML, OIDC, Entra, AD, Keycloak) | 🟡 | Entra/Google/Keycloak؛ **SAML start/ACS** — `sso-roadmap-AR.md` |
| 3 | حزمة أمن مؤسسية | 🟡 | `enterprise-security/` + `penetration-testing-AR.md` |
| 4 | ISO 27001 | 🟡 | `iso27001-readiness-AR.md` |
| 5 | متعدد القطاعات | ✅ | `platform/sector` · 7 قطاعات |
| 6 | UX موحّد | 📋 | `ux-maturity-charter-AR.md` |
| 7 | تقارير تنفيذية PDF | 🟡 | `reports/executive_report.py` · `reporting-roadmap-AR.md` |
| 8 | RBAC موسّع | 🟡 | auditor read-only؛ 6 أدوار في `rbac/enforcement.py` |
| 9 | أرشفة Retention / Legal Hold | 🟡 | `governance/routes.py` · `retention-and-archive-AR.md` |
| 10 | مراقبة SLA | 🟡 | `operations/sla-monitoring-AR.md` · Grafana |
| 11 | وثائق بنية وAPI وتشغيل | 🟡 | `architecture/README.md` · `operations/runbooks-AR.md` |
| 12 | On-Prem / حكومي / Air-gap | 🟡 | `private-cloud-helm-AR.md` · `air-gapped-playbook-AR.md` |
| 13 | Audit trail غير قابل للتلاعب | 🟡 | `audit/immutable.py` · `audit-trail-immutable-AR.md` |
| 14 | Data governance | 🟡 | `data-governance-AR.md` |
| 15 | تعميق DATEV/SAP/Oracle/M365 | 🟡 | `integrations/enterprise-integrations-AR.md` |
| 16 | i18n 100% | 🟡 | `scripts/check_i18n_coverage.py` |
| 17 | WCAG / Accessibility | 📋 | `engineering/accessibility-AR.md` |
| 18 | Data residency | 🟡 | migration 017 · `multi-region-deployment-AR.md` |
| 19 | Customer Success Portal | 📋 | `commercial/customer-success-portal-AR.md` |
| 20 | بيئات Dev/UAT/Prod للعملاء | 🟡 | `commercial/dedicated-environments-AR.md` |
| 21 | SLA Management | 🟡 | `operations/sla-management-AR.md` |
| 22 | Business Continuity | 🟡 | `disaster-recovery-AR.md` · `business-continuity-AR.md` |
| 23 | Hardware Certification | 📋 | `commercial/hardware-certification-AR.md` |
| 24 | Knowledge Base | 📋 | `commercial/knowledge-base-AR.md` |
| 25 | برنامج شركاء | 📋 | `commercial/partners-program-AR.md` |
| 26 | إثبات Tenant isolation | 🟡 | `governance/tenant-isolation-AR.md` |
| 27 | Change / Release Management | 🟡 | `operations/change-release-management-AR.md` |
| 28 | Backup RTO/RPO + اختبار استعادة | 🟡 | `enterprise-backup-restore-runbook.md` |
| 29 | تركيز النواة | ✅ | `platform-vision-AR.md` · `stability-charter-AR.md` |
| 30 | Enterprise / Government Edition | 📋 | `editions/enterprise-government-edition-AR.md` |

**رموز:** ✅ جاهز · 🟡 جزئي · 📋 مخطَّط/تجاري

---

## المرحلة A — استقرار (8–12 أسبوعاً)

1. إكمال نقل **login → access → billing** من `server.py`
2. SAML ACS + Redis لـ SSO state
3. اختبارات CI لكل domain
4. Pentest خارجي (بند 3)
5. RBAC فرض على مسارات حساسة

## المرحلة B — امتثال وبيع (3–6 أشهر)

ISO pack · تقارير PDF موحّدة · tenant isolation report · SLA contracts

## المرحلة C — حكومي / سيادي

Helm hardened · air-gap · WORM audit · SIEM

## المرحلة D — نضج مستمر

UX · i18n · WCAG · KB · شركاء · Customer Success

---

## ما لن نفعله الآن

- Marketplace / تكاملات عرضية بدون عميل ملزم
- موجات AI جديدة قبل استقرار التشغيل

---

## روابط سريعة

- [تفكيك server.py](./engineering/server-decomposition-roadmap.md)
- [أمن مؤسسي](./enterprise-security/README.md)
- [Domains README](../backend/app/domains/README.md)
- [إعادة التموضع](./product-repositioning-AR.md)
