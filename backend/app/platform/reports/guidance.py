"""Rule-based operational guidance (decision support, no LLM required)."""
from __future__ import annotations

from typing import Any


def build_operational_guidance(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Return prioritized recommendations for admins."""
    items: list[dict[str, Any]] = []
    kpis = snapshot.get("kpis") or {}

    overdue_count = int(kpis.get("overdueInvoiceCount") or 0)
    overdue_total = float(kpis.get("overdueTotal") or 0)
    if overdue_count > 0:
        items.append(
            {
                "priority": "high",
                "code": "overdue_invoices",
                "titleDe": "Überfällige Rechnungen prüfen",
                "titleAr": "مراجعة الفواتير المتأخرة",
                "detailDe": f"{overdue_count} Rechnung(en), Summe ca. {overdue_total:.2f} EUR.",
                "detailAr": f"{overdue_count} فاتورة متأخرة بمجموع تقريبي {overdue_total:.2f} يورو.",
                "action": "open_invoices",
            }
        )

    locked = int(kpis.get("lockedCompanies") or 0)
    if locked > 0:
        items.append(
            {
                "priority": "medium",
                "code": "locked_companies",
                "titleDe": "Gesperrte Firmen freigeben oder kontaktieren",
                "titleAr": "مراجعة الشركات المقفلة",
                "detailDe": f"{locked} Firma(en) sind gesperrt.",
                "detailAr": f"{locked} شركة في حالة مقفلة.",
                "action": "open_companies",
            }
        )

    workers_on_site = int(snapshot.get("workersOnSite") or kpis.get("workersOnSite") or 0)
    sec = snapshot.get("security") or {}
    open_findings = int(sec.get("openFindings") or len(sec.get("findings") or []))
    if open_findings > 0:
        items.append(
            {
                "priority": "high",
                "code": "security_findings",
                "titleDe": "Sicherheits-Findings bearbeiten",
                "titleAr": "معالجة تنبيهات الأمان",
                "detailDe": f"{open_findings} offene Finding(s).",
                "detailAr": f"{open_findings} تنبيه أمني مفتوح.",
                "action": "open_security",
            }
        )

    if snapshot.get("activeEmergency"):
        items.append(
            {
                "priority": "critical",
                "code": "active_emergency",
                "titleDe": "Aktiver Notfall — Sofortmaßnahmen",
                "titleAr": "حالة طوارئ نشطة — إجراء فوري",
                "detailDe": "Notfallmodus ist aktiv. Command Center öffnen.",
                "detailAr": "وضع الطوارئ مفعّل. افتح مركز القيادة.",
                "action": "open_emergency",
            }
        )

    access = snapshot.get("accessDaily") or []
    if access:
        last = access[-1]
        check_in = int(last.get("checkIn") or 0)
        check_out = int(last.get("checkOut") or 0)
        if check_in > 0 and check_out < max(1, check_in // 2):
            items.append(
                {
                    "priority": "medium",
                    "code": "checkout_gap",
                    "titleDe": "Fehlende Check-outs heute",
                    "titleAr": "تسجيل خروج ناقص اليوم",
                    "detailDe": "Viele Check-ins ohne ausreichende Check-outs — Team erinnern.",
                    "detailAr": "عدد كبير من الدخول دون خروج كافٍ — تذكير الفريق.",
                    "action": "open_access_logs",
                }
            )

    if workers_on_site == 0 and not items:
        items.append(
            {
                "priority": "info",
                "code": "site_empty",
                "titleDe": "Keine Mitarbeiter auf der Baustelle",
                "titleAr": "لا يوجد عمال في الموقع حالياً",
                "detailDe": "Live-Status: 0 Personen vor Ort.",
                "detailAr": "الحالة الحية: لا أحد في الموقع.",
                "action": "open_ops_map",
            }
        )

    if not items:
        items.append(
            {
                "priority": "info",
                "code": "all_clear",
                "titleDe": "Keine kritischen Aktionen",
                "titleAr": "لا إجراءات حرجة",
                "detailDe": "Systemstatus stabil — weiter beobachten.",
                "detailAr": "الوضع مستقر — استمر بالمراقبة.",
                "action": "none",
            }
        )
    return items
