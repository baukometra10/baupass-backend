"""Certificate HTML matching WorkPass Lohn portal print views (Form VB + LStB)."""
from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

_MONTHS_DE = (
    "",
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _amt(value: Any) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if n < 0 else ""
    n = abs(n)
    whole = int(n)
    cents = int(round((n - whole) * 100))
    if cents == 100:
        whole += 1
        cents = 0
    whole_s = f"{whole:,}".replace(",", ".")
    return f"{sign}{whole_s},{cents:02d}"


def format_period_label_de(period: Any) -> str:
    """YYYY-MM → 'August 2026' (WorkPass Lohn formatPeriodLabel)."""
    p = str(period or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})$", p)
    if not m:
        return p
    year, month = m.group(1), int(m.group(2))
    if 1 <= month <= 12:
        return f"{_MONTHS_DE[month]} {year}"
    return p


def format_date_de(value: Any) -> str:
    """YYYY-MM-DD → 01.01.2001"""
    if not value:
        return "—"
    s = str(value).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    return s


def _split_money_parts(value: Any) -> tuple[str, str]:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—", "—"
    sign = "-" if n < 0 else ""
    n = abs(n)
    whole = int(n)
    cents = int(round((n - whole) * 100))
    if cents == 100:
        whole += 1
        cents = 0
    return f"{sign}{whole}", f"{cents:02d}"


_VB_CSS = """
@page { size: A4 portrait; margin: 0; }
html, body { margin: 0; padding: 0; background: #fff; }
.verdienst-sheet {
  width: 210mm; min-height: 297mm; margin: 0 auto; background: #fff; color: #000;
  box-sizing: border-box;
}
.verdienst-document.vb-sheet-a4 {
  width: 210mm; min-height: 297mm; max-width: 210mm; margin: 0 auto;
  background: #fff; box-sizing: border-box;
  padding: 8mm 9mm; border: 1px solid #000;
  font-family: Arial, Helvetica, sans-serif; color: #000;
  display: flex; flex-direction: column; gap: 3.5mm;
}
.vb-header { flex: 0 0 auto; }
.vb-header-top {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 4mm;
  border-bottom: 1.2pt solid #1a2a33; padding-bottom: 2.5mm;
}
.vb-kicker {
  margin: 0 0 1mm; font-size: 7pt; color: #475569;
  text-transform: uppercase; letter-spacing: 0.04em;
}
.vb-title { margin: 0; font-size: 14pt; font-weight: 700; }
.vb-header-period {
  text-align: right; min-width: 42mm; border: 0.5pt solid #1a2a33;
  padding: 2mm 2.5mm; background: #f8fafc;
}
.vb-header-period span, .vb-header-period em {
  display: block; font-size: 6.5pt; font-style: normal; color: #475569;
}
.vb-header-period strong { display: block; font-size: 11pt; margin: 0.6mm 0; }
.vb-sub { margin: 0; font-size: 7.5pt; color: #334155; }
.vb-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 3mm; flex: 0 0 auto; }
.vb-party { border: 0.5pt solid #1a2a33; padding: 2.5mm 3mm; min-height: 42mm; }
.vb-party h3 {
  margin: 0 0 1.5mm; font-size: 7pt; text-transform: uppercase;
  letter-spacing: 0.05em; border-bottom: 0.35pt solid #cbd5e1; padding-bottom: 1mm;
}
.vb-party pre {
  margin: 0 0 2mm; white-space: pre-wrap; font-family: inherit;
  font-size: 8.5pt; line-height: 1.35;
}
.vb-meta-table { width: 100%; border-collapse: collapse; font-size: 7.2pt; }
.vb-meta-table td { padding: 0.7mm 0; vertical-align: top; }
.vb-meta-table td:first-child { color: #475569; width: 42%; }
.vb-months { margin: 2mm 0 0; font-size: 6.5pt; color: #475569; line-height: 1.3; }
.portal-vb-table.vb-amounts {
  width: 100%; border-collapse: collapse; font-size: 8.5pt; flex: 1 1 auto;
}
.portal-vb-table th, .portal-vb-table td {
  border: 0.45pt solid #334155; padding: 1.6mm 2mm;
}
.portal-vb-table th {
  background: #e8eef2; text-align: left; font-size: 7pt;
  text-transform: uppercase; letter-spacing: 0.04em; font-weight: 700;
}
.portal-vb-table .num {
  text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; width: 28mm;
}
.portal-vb-table tr.vb-deduction td { color: #334155; }
.vb-footer {
  margin-top: auto; padding-top: 2mm; border-top: 0.4pt solid #94a3b8;
  font-size: 6.5pt; color: #475569; flex: 0 0 auto;
}
.vb-footer p { margin: 0 0 0.8mm; }
.vb-legal { font-style: italic; }
"""

_LSTB_CSS = """
@page { size: A4 portrait; margin: 0; }
html, body { margin: 0; padding: 0; background: #fff; }
.lstb-sheet { width: 210mm; min-height: 297mm; margin: 0 auto; background: #fff; }
.lstb-document {
  width: 210mm; min-height: 297mm; max-width: 210mm; margin: 0 auto;
  box-sizing: border-box; padding: 6mm 7mm 5mm;
  font-family: Arial, Helvetica, sans-serif; font-size: 7pt; color: #000;
  display: flex; flex-direction: column; background: #fff;
}
.lstb-official-header {
  display: grid; grid-template-columns: 1.05fr 1.5fr 0.85fr; gap: 3mm;
  align-items: start; margin-bottom: 2.5mm; flex: 0 0 auto;
}
.lstb-finanzamt { margin: 0 0 1mm; font-size: 6.5pt; text-transform: uppercase; letter-spacing: .04em; color: #334155; }
.lstb-finanzamt-val {
  margin: 0; border: 0.7pt solid #111; padding: 2.2mm 2.5mm; min-height: 10mm;
  font-size: 9pt; font-weight: 700; background: #fff;
}
.lstb-finanzamt-hint { margin: 1.2mm 0 0; font-size: 5.8pt; color: #475569; line-height: 1.25; }
.lstb-header-center { text-align: center; }
.lstb-header-center h2 { margin: 0 0 1mm; font-size: 13pt; font-weight: 700; }
.lstb-header-center p { margin: 0 0 0.8mm; font-size: 7.5pt; }
.lstb-recipient { font-weight: 700; text-transform: uppercase; letter-spacing: .03em; font-size: 7pt !important; }
.lstb-emp-name { font-size: 11pt !important; font-weight: 700; margin-top: 1mm !important; }
.lstb-sub { font-size: 5.8pt !important; color: #334155; line-height: 1.3; }
.lstb-header-right { text-align: right; font-size: 6.5pt; color: #334155; }
.lstb-kmid { margin: 1mm 0 0; font-size: 9pt; font-weight: 700; color: #111; }
.lstb-title-block-secondary {
  border-top: 0.6pt solid #111; border-bottom: 2.2pt solid #111;
  padding: 1.4mm 0; margin-bottom: 3mm; text-align: center; flex: 0 0 auto;
}
.lstb-title-block-secondary p { margin: 0; font-size: 7pt; }
.lstb-grid {
  display: grid; grid-template-columns: 0.92fr 1.08fr; gap: 0;
  flex: 1 1 auto; min-height: 0; align-items: stretch;
  border: 0.7pt solid #111;
}
.lstb-left { display: flex; flex-direction: column; gap: 2.5mm; padding: 2mm; border-right: 0.7pt solid #111; }
.lstb-meta-table {
  width: 100%; border-collapse: collapse; border: 0.6pt solid #111; font-size: 7pt;
}
.lstb-meta-table td { border-bottom: 0.35pt solid #cbd5e1; padding: 1.1mm 1.6mm; vertical-align: top; }
.lstb-meta-table tr:last-child td { border-bottom: 0; }
.lstb-lbl { width: 46%; color: #334155; background: #f8fafc; }
.lstb-address-block { border: 0.6pt solid #111; padding: 2mm 2.4mm; }
.lstb-block-h {
  font-size: 6.5pt; text-transform: uppercase; letter-spacing: .04em;
  border-bottom: 0.35pt solid #cbd5e1; padding-bottom: 1mm; margin-bottom: 1.5mm;
}
.lstb-address-block pre {
  margin: 0; white-space: pre-wrap; font-family: inherit; font-size: 8pt; line-height: 1.35;
}
.lstb-months-summary { margin: 0; font-size: 6.2pt; color: #334155; line-height: 1.3; }
.lstb-right { min-height: 0; padding: 0; }
.lstb-rows-table {
  width: 100%; height: 100%; border-collapse: collapse; border: 0; font-size: 6.4pt;
}
.lstb-rows-table th, .lstb-rows-table td {
  border: 0.35pt solid #334155; padding: 0.9mm 1.2mm; vertical-align: middle;
}
.lstb-rows-table th {
  background: #e8eef2; text-align: left; font-size: 6pt;
  text-transform: uppercase; letter-spacing: .03em;
}
.lstb-nr { width: 8mm; text-align: center !important; font-weight: 700; }
.lstb-euro, .lstb-cent {
  width: 14mm; text-align: right !important; font-variant-numeric: tabular-nums; white-space: nowrap;
}
.lstb-rows-table .lstb-empty td.lstb-euro,
.lstb-rows-table .lstb-empty td.lstb-cent { color: transparent; }
.lstb-rows-table .lstb-reserved .lstb-desc { color: #94a3b8; }
.lstb-text td.lstb-euro { text-align: left !important; }
.lstb-footer-note {
  margin-top: auto; padding-top: 2.5mm; border-top: 1.4pt solid #111;
  font-size: 6pt; color: #334155; flex: 0 0 auto;
}
.lstb-footer-note p { margin: 0; line-height: 1.35; }
"""


def build_verdienst_certificate_html(doc: dict[str, Any] | None, *, meta: dict[str, Any] | None = None) -> str:
    """HTML matching Lohn portal renderVerdienstPrintHtml exactly."""
    d = doc if isinstance(doc, dict) else {}
    m = meta if isinstance(meta, dict) else {}
    year = str(d.get("year") or m.get("year") or (str(d.get("period") or "")[:4]) or "").strip()
    period = str(d.get("period") or m.get("period") or "").strip()[:7]
    period_label = format_period_label_de(period) or period or "—"
    emp_name = str(d.get("employeeName") or m.get("employeeName") or "").strip()
    emp_addr = str(d.get("employeeAddress") or "").strip()
    emp_block = "\n".join(x for x in (emp_name, emp_addr) if x) or emp_name or "—"
    seller = str(d.get("seller") or m.get("companyName") or "").strip() or "—"
    months = d.get("monthsInYear") if isinstance(d.get("monthsInYear"), list) else []
    months_label = ", ".join(format_period_label_de(x) or str(x) for x in months) if months else ""
    rows = d.get("rows") if isinstance(d.get("rows"), list) else []
    body_rows: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cls = ' class="vb-deduction"' if row.get("deduction") else ""
        body_rows.append(
            f"<tr{cls}><td>{_esc(row.get('label'))}</td>"
            f"<td class=\"num\">{_esc(_amt(row.get('monthly')))}</td>"
            f"<td class=\"num\">{_esc(_amt(row.get('yearly')))}</td></tr>"
        )
    if not body_rows:
        totals = d.get("totals") if isinstance(d.get("totals"), dict) else {}
        ytd = d.get("ytd") if isinstance(d.get("ytd"), dict) else {}
        monthly = d.get("monthly") if isinstance(d.get("monthly"), dict) else {}
        pairs = [
            ("Abrechnungs-Brutto", "gross"),
            ("Steuer-Brutto", "taxGross"),
            ("SV-Brutto", "svGross"),
            ("Gesamt-Brutto mtl.", "gross"),
            ("Nettoentgelt mtl.", "net"),
            ("Lohnsteuer", "payrollTax"),
            ("Solidaritätszuschlag", "solidarity"),
            ("Kirchensteuer", "churchTax"),
            ("KV-Beitrag", "health"),
            ("RV-Beitrag", "pension"),
            ("PV-Beitrag", "care"),
            ("AV-Beitrag", "unemployment"),
            ("Netto-Verdienst", "net"),
        ]
        for label, key in pairs:
            mtl = monthly.get(key)
            if mtl is None:
                mtl = totals.get(key)
            jahr = ytd.get(key)
            if jahr is None:
                jahr = mtl
            body_rows.append(
                f"<tr><td>{_esc(label)}</td>"
                f"<td class=\"num\">{_esc(_amt(mtl))}</td>"
                f"<td class=\"num\">{_esc(_amt(jahr))}</td></tr>"
            )

    stamped = datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"/><title>Verdienstbescheinigung</title>
<style>{_VB_CSS}</style></head>
<body>
<div class="verdienst-sheet">
  <article class="verdienst-document vb-sheet-a4">
    <header class="vb-header">
      <div class="vb-header-top">
        <div>
          <p class="vb-kicker">WorkPass Lohn · Form VB</p>
          <h2 class="vb-title">Verdienstbescheinigung</h2>
        </div>
        <div class="vb-header-period">
          <span>Bezugsmonat</span>
          <strong>{_esc(period_label)}</strong>
          <em>Jahr {_esc(year or period[:4])}</em>
        </div>
      </div>
      <p class="vb-sub">Ausdruck für den Arbeitnehmer · Beträge aus freigegebenen Monatsabrechnungen</p>
    </header>
    <div class="vb-grid">
      <section class="vb-party">
        <h3>Arbeitnehmer/in</h3>
        <pre>{_esc(emp_block)}</pre>
        <table class="vb-meta-table">
          <tr><td>Personal-Nr.</td><td>{_esc(d.get("personnelNumber") or d.get("employeeId") or "—")}</td></tr>
          <tr><td>Identifikationsnummer</td><td>{_esc(d.get("employeeTaxId") or "—")}</td></tr>
          <tr><td>SV-Nummer</td><td>{_esc(d.get("employeeInsuranceNo") or "—")}</td></tr>
          <tr><td>Geburtsdatum</td><td>{_esc(format_date_de(d.get("employeeBirthDate")))}</td></tr>
          <tr><td>Steuerklasse</td><td>{_esc(str(d.get("taxClass") or "I").strip() or "I")}</td></tr>
        </table>
      </section>
      <section class="vb-party">
        <h3>Arbeitgeber</h3>
        <pre>{_esc(seller)}</pre>
        <table class="vb-meta-table">
          <tr><td>Steuernummer</td><td>{_esc(d.get("taxNumber") or "—")}</td></tr>
          <tr><td>Abgerechnete Monate {_esc(year)}</td><td>{_esc(d.get("monthsCount") or len(months) or "—")}</td></tr>
        </table>
        <p class="vb-months">{_esc(months_label)}</p>
      </section>
    </div>
    <table class="portal-vb-table vb-amounts">
      <thead>
        <tr>
          <th>Bezeichnung</th>
          <th class="num">mtl. ({_esc(period_label)})</th>
          <th class="num">Jahr {_esc(year or "")}</th>
        </tr>
      </thead>
      <tbody>{"".join(body_rows)}</tbody>
    </table>
    <footer class="vb-footer">
      <p>mtl. = Bezugsmonat · Jahr = Summe freigegebener Monate {_esc(year)}</p>
      <p class="vb-legal">Ausdruck für den Arbeitnehmer · nicht Bestandteil der Monatsabrechnung · {_esc(stamped)}</p>
    </footer>
  </article>
</div>
</body></html>
"""


def build_lstb_certificate_html(doc: dict[str, Any] | None, *, meta: dict[str, Any] | None = None) -> str:
    """HTML matching Lohn portal renderLstbPrintHtml."""
    d = doc if isinstance(doc, dict) else {}
    m = meta if isinstance(meta, dict) else {}
    year = str(d.get("year") or m.get("year") or "").strip() or str(datetime.now().year)
    tax_number = str(d.get("taxNumber") or "").strip()
    finanzamt = tax_number or "— bitte Steuernummer der Firma eintragen —"
    finanzamt_hint = (
        "Steuernummer der Firma (Betriebsstättenfinanzamt) · nicht Wohnsitzfinanzamt des Mitarbeiters"
        if tax_number
        else "Firma → Steuer-Nr. eintragen (z. B. 143/123/45678)"
    )
    period_dates = str(d.get("certPeriod") or "—")
    period_von_bis = str(d.get("certPeriodLabel") or "")
    try:
        church_rate = float(d.get("churchTaxRate") or 0)
    except (TypeError, ValueError):
        church_rate = 0.0
    church = f"{church_rate:g} %" if church_rate > 0 else "keine"
    emp_name = str(d.get("employeeName") or m.get("employeeName") or "").strip() or "—"
    emp_addr = str(d.get("employeeAddress") or "").strip()
    emp_block = "\n".join(x for x in (emp_name, emp_addr) if x) or emp_name
    totals = d.get("totals") if isinstance(d.get("totals"), dict) else {}
    months = totals.get("months") if isinstance(totals.get("months"), list) else (
        d.get("monthsInYear") if isinstance(d.get("monthsInYear"), list) else []
    )
    months_count = totals.get("monthsCount") if totals.get("monthsCount") is not None else (
        d.get("monthsCount") or len(months)
    )
    has_data = bool(d.get("hasData") if d.get("hasData") is not None else months)
    months_summary = (
        f"Abgerechnete Monate {year}: {', '.join(str(x) for x in months)} ({months_count} Monat(e))"
        if has_data
        else f"Keine freigegebenen Monate für {year}."
    )
    tax_id = re.sub(r"\D", "", str(d.get("employeeTaxId") or ""))
    tax_id_display = tax_id if len(tax_id) == 11 else "—"
    pers = str(d.get("personnelNumber") or d.get("employeeId") or "0000")
    pers_clean = re.sub(r"\W", "", pers)[:8]
    km_id = str(d.get("kmId") or f"FD{year}{pers_clean}")
    zeitraum = f"{period_von_bis} ({period_dates})" if period_von_bis else period_dates

    rows = d.get("rows") if isinstance(d.get("rows"), list) else []
    body_rows: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "")
        is_reserved = key.startswith("empty")
        cls = ' class="lstb-reserved lstb-empty"' if is_reserved else ""
        nr = _esc(row.get("nr"))
        label = _esc(row.get("label"))
        if row.get("money"):
            euro, cent = _split_money_parts(row.get("value"))
            body_rows.append(
                f"<tr{cls}><td class=\"lstb-nr\">{nr}</td><td class=\"lstb-desc\">{label}</td>"
                f"<td class=\"lstb-euro\">{_esc(euro)}</td><td class=\"lstb-cent\">{_esc(cent)}</td></tr>"
            )
        elif key == "certPeriod":
            body_rows.append(
                f"<tr class=\"lstb-text\"><td class=\"lstb-nr\">{nr}</td><td class=\"lstb-desc\">{label}</td>"
                f"<td class=\"lstb-euro\" colspan=\"2\">{_esc(row.get('value') or '—')}</td></tr>"
            )
        else:
            body_rows.append(
                f"<tr{cls}><td class=\"lstb-nr\">{nr}</td><td class=\"lstb-desc\">{label}</td>"
                f"<td class=\"lstb-euro\">{_esc(row.get('value') if row.get('value') is not None else '')}</td>"
                f"<td class=\"lstb-cent\"></td></tr>"
            )

    footer = (
        f"Bescheinigung nach § 41b EStG für den Arbeitnehmer · nicht LStA der Firma (§ 41a EStG) · "
        f"{year} · {months_count} Monat(e) · LSt BMF PAP · SV SGB IV"
    )
    legal_sub = (
        "Elektronische Lohnsteuerbescheinigung nach § 41b EStG · für den Arbeitnehmer · "
        "nicht die LStA der Firma (§ 41a EStG)"
    )
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"/><title>Lohnsteuerbescheinigung</title>
<style>{_LSTB_CSS}</style></head>
<body>
<div class="lstb-sheet">
  <article class="lstb-document">
    <header class="lstb-official-header">
      <div class="lstb-header-left">
        <p class="lstb-finanzamt">Finanzamt / Gemeinde</p>
        <p class="lstb-finanzamt-val">{_esc(finanzamt)}</p>
        <p class="lstb-finanzamt-hint">{_esc(finanzamt_hint)}</p>
      </div>
      <div class="lstb-header-center">
        <h2>Lohnsteuerbescheinigung</h2>
        <p>für das Kalenderjahr <strong>{_esc(year)}</strong></p>
        <p class="lstb-recipient">für den Arbeitnehmer</p>
        <p class="lstb-emp-name">{_esc(emp_name)}</p>
        <p class="lstb-sub">{_esc(legal_sub)}</p>
      </div>
      <div class="lstb-header-right">
        <p>KmId</p>
        <p class="lstb-kmid">{_esc(km_id)}</p>
      </div>
    </header>
    <header class="lstb-title-block lstb-title-block-secondary">
      <p>WorkPass Lohn · BMF PAP / SGB IV · Jahr <strong>{_esc(year)}</strong></p>
    </header>
    <div class="lstb-grid">
      <div class="lstb-left">
        <table class="lstb-meta-table">
          <tbody>
            <tr><td class="lstb-lbl">Personal-Nr.</td><td>{_esc(d.get("personnelNumber") or d.get("employeeId") or "—")}</td></tr>
            <tr><td class="lstb-lbl">Steuer-ID (Mitarbeiter)</td><td>{_esc(tax_id_display)}</td></tr>
            <tr><td class="lstb-lbl">SV-Nummer</td><td>{_esc(d.get("employeeInsuranceNo") or "—")}</td></tr>
            <tr><td class="lstb-lbl">Geburtsdatum</td><td>{_esc(format_date_de(d.get("employeeBirthDate")))}</td></tr>
            <tr><td class="lstb-lbl">Steuerklasse</td><td>{_esc(str(d.get("taxClass") or "I").strip() or "I")}</td></tr>
            <tr><td class="lstb-lbl">Kinderfreibeträge (ZKF)</td><td>{_esc(d.get("childAllowanceFactor") if d.get("childAllowanceFactor") is not None else 0)}</td></tr>
            <tr><td class="lstb-lbl">Kirchensteuer</td><td>{_esc(church)}</td></tr>
            <tr><td class="lstb-lbl">Zeitraum</td><td>{_esc(zeitraum)}</td></tr>
          </tbody>
        </table>
        <div class="lstb-address-block">
          <div class="lstb-block-h">Arbeitnehmer/in</div>
          <pre>{_esc(emp_block)}</pre>
        </div>
        <div class="lstb-address-block">
          <div class="lstb-block-h">Arbeitgeber</div>
          <pre>{_esc(d.get("seller") or "—")}</pre>
        </div>
        <p class="lstb-months-summary">{_esc(months_summary)}</p>
      </div>
      <div class="lstb-right">
        <table class="lstb-rows-table">
          <thead>
            <tr>
              <th class="lstb-nr">Nr.</th>
              <th class="lstb-desc">Bezeichnung</th>
              <th class="lstb-euro">Euro</th>
              <th class="lstb-cent">Cent</th>
            </tr>
          </thead>
          <tbody>{"".join(body_rows)}</tbody>
        </table>
      </div>
    </div>
    <footer class="lstb-footer-note">
      <p>{_esc(footer)}</p>
    </footer>
  </article>
</div>
</body></html>
"""


def build_certificate_html(
    doc: dict[str, Any] | None,
    *,
    meta: dict[str, Any] | None = None,
    doc_type: str = "",
) -> str:
    """Pick Verdienst or LStB template from document type."""
    dtype = str(doc_type or (meta or {}).get("docType") or (meta or {}).get("documentType") or "").strip().lower()
    title = str((meta or {}).get("title") or (doc or {}).get("title") or "").lower()
    if dtype in {"lohnsteuerbescheinigung", "lstb"} or "lohnsteuer" in title or "lstb" in title:
        return build_lstb_certificate_html(doc, meta=meta)
    return build_verdienst_certificate_html(doc, meta=meta)
