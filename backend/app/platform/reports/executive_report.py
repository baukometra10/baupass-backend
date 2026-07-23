"""Executive summary PDF for leadership."""
from __future__ import annotations

from typing import Any


def build_executive_summary_pdf(
    *,
    company_name: str,
    snapshot: dict[str, Any],
    reporting_summary: dict[str, Any] | None = None,
    branding: dict[str, Any] | None = None,
    terms: dict[str, str] | None = None,
) -> bytes:
    from backend.app.platform.reports.report_pdf_layout import build_branded_narrative_report_pdf

    brand = dict(branding or {})
    if company_name:
        brand["companyName"] = company_name
    workers = str((terms or {}).get("termWorkers") or "Mitarbeiter").strip()
    site = str((terms or {}).get("termSite") or "Baustelle").strip()

    sections: list[dict[str, Any]] = []
    kpis = (reporting_summary or {}).get("kpis") or snapshot.get("kpis") or {}
    if kpis:
        sections.append(
            {
                "title": "Finanzen & Compliance",
                "kpi_labels": (
                    ("paidTotal", "Bezahlt"),
                    ("openTotal", "Offen"),
                    ("overdueInvoiceCount", "Überfällige Rechnungen"),
                    ("overdueTotal", "Überfällig"),
                    ("lockedCompanies", "Gesperrte Mandanten"),
                    ("suspensionsLast30d", "Auto-Sperren (30 Tage)"),
                ),
                "kpis": kpis,
            }
        )

    on_site = snapshot.get("workersOnSite") or snapshot.get("onSiteCount")
    if on_site is not None:
        sections.append({"title": "Operations", "lines": [f"{workers} am Standort ({site}): {on_site}"]})

    hr = snapshot.get("hrCompliance") or {}
    if hr:
        sections.append(
            {
                "title": "HR / Compliance",
                "lines": [f"{k}: {v}" for k, v in list(hr.items())[:12]],
            }
        )

    guidance = snapshot.get("guidance") or []
    if isinstance(guidance, list) and guidance:
        bullets = []
        for item in guidance[:5]:
            if isinstance(item, dict):
                bullets.append(str(item.get("title") or item.get("message") or item))
        sections.append({"title": "Top-Empfehlungen", "bullets": bullets})

    return build_branded_narrative_report_pdf(
        report_title="Executive Summary",
        subtitle=f"Management-Kurzbericht · {company_name or '-'}",
        branding=brand,
        sections=sections,
    )
