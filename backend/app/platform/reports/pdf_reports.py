"""Generate platform operational reports as PDF (ReportLab, company branding)."""
from __future__ import annotations

from typing import Any


def build_operations_report_pdf(
    *,
    title: str,
    company_name: str,
    snapshot: dict[str, Any],
    guidance: list[dict[str, Any]] | None = None,
    branding: dict[str, Any] | None = None,
    terms: dict[str, str] | None = None,
) -> bytes:
    from backend.app.platform.reports.report_pdf_layout import build_branded_narrative_report_pdf

    brand = dict(branding or {})
    if company_name and not brand.get("companyName"):
        brand["companyName"] = company_name
    workers = str((terms or {}).get("termWorkers") or "Mitarbeiter").strip()
    site = str((terms or {}).get("termSite") or "Baustelle").strip()

    sections: list[dict[str, Any]] = []

    kpis = snapshot.get("kpis") or {}
    if kpis:
        sections.append(
            {
                "title": "KPIs",
                "kpi_labels": (
                    ("paidTotal", "Bezahlt"),
                    ("openTotal", "Offen"),
                    ("overdueInvoiceCount", "Überfällige Rechnungen"),
                    ("overdueTotal", "Überfällig (Summe)"),
                    ("lockedCompanies", "Gesperrte Firmen"),
                    ("workersOnSite", f"{workers} am Standort ({site})"),
                ),
                "kpis": kpis,
            }
        )

    hr = snapshot.get("hrCompliance") or {}
    if hr:
        sections.append(
            {
                "title": "Lohn & Compliance",
                "lines": [
                    f"{workers} gesamt: {hr.get('workersTotal', 0)}",
                    f"Pflichtdokumente fehlend/abgelaufen: {hr.get('workersMissingRequiredDocs', 0)}",
                    f"Abgelaufene Dokumente ({workers}): {hr.get('workersWithExpiredDocs', 0)}",
                    f"Läuft in 14 Tagen ab: {hr.get('workersExpiringDocs14d', 0)}",
                    f"Lohnabrechnungen ({hr.get('period', '-')}): {hr.get('payrollDocsThisMonth', 0)}",
                    f"Posteingang ungelesen: {hr.get('inboxUnread', 0)}",
                    f"DATEV verbunden: {'ja' if hr.get('datevConnected') else 'nein'}",
                ],
            }
        )

    access = snapshot.get("accessDaily") or []
    if access:
        sections.append(
            {
                "title": "Zutritte (7 Tage)",
                "lines": [
                    f"{row.get('day', '-')}: Check-in {row.get('checkIn', 0)} / Check-out {row.get('checkOut', 0)}"
                    for row in access[-7:]
                ],
            }
        )

    sec = snapshot.get("security") or {}
    if sec:
        sections.append(
            {
                "title": "Sicherheit",
                "lines": [f"Offene Findings: {sec.get('openFindings', len(sec.get('findings') or []))}"],
            }
        )

    layers = snapshot.get("enterpriseLayers") or {}
    if layers:
        sections.append(
            {
                "title": "Enterprise (6 Ebenen)",
                "lines": [f"{layer_name}: {summary}" for layer_name, summary in layers.items()],
            }
        )

    if guidance:
        bullets = []
        for item in guidance[:12]:
            pri = str(item.get("priority") or "info").upper()
            title_de = str(item.get("titleDe") or item.get("titleAr") or item.get("title") or "")
            detail = str(item.get("detailDe") or item.get("detailAr") or item.get("detail") or "")
            line = f"[{pri}] {title_de}"
            if detail:
                line += f" — {detail[:120]}"
            bullets.append(line)
        sections.append({"title": "Empfohlene Maßnahmen", "bullets": bullets})

    subtitle = f"Firma: {company_name or '-'} · Operations Report"
    return build_branded_narrative_report_pdf(
        report_title=title,
        subtitle=subtitle,
        branding=brand,
        sections=sections,
    )
