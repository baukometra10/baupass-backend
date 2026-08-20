"""Verdienstbescheinigung / LStB HTML matching WorkPass Lohn portal print layout."""
from __future__ import annotations

import html
from typing import Any


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


_VB_CSS = """
@page { size: A4 portrait; margin: 0; }
html, body { margin: 0; padding: 0; background: #fff; }
.verdienst-sheet {
  width: 210mm; height: 297mm; max-height: 297mm; margin: 0 auto; background: #fff; color: #111;
  box-sizing: border-box; border: 1px solid #111; overflow: hidden;
}
.verdienst-document {
  height: 100%; box-sizing: border-box;
  padding: 9mm 11mm 8mm;
  font-family: Arial, Helvetica, sans-serif;
  font-size: 9pt; line-height: 1.3;
  display: flex; flex-direction: column;
}
.vb-header { border-bottom: 1.5px solid #111; padding-bottom: 3.5mm; margin-bottom: 4.5mm; flex: 0 0 auto; }
.vb-header-top { display: flex; justify-content: space-between; gap: 8mm; align-items: flex-start; }
.vb-kicker { margin: 0; font-size: 7.5pt; letter-spacing: .05em; color: #555; text-transform: uppercase; }
.vb-title { margin: 1mm 0 0; font-size: 15pt; font-weight: 700; letter-spacing: .01em; }
.vb-header-period { text-align: right; font-size: 9pt; }
.vb-header-period span { display: block; color: #555; font-size: 7.5pt; }
.vb-header-period strong { display: block; font-size: 11.5pt; margin-top: 1mm; }
.vb-header-period em { display: block; font-style: normal; color: #333; margin-top: 1mm; }
.vb-sub { margin: 2.5mm 0 0; font-size: 7.5pt; color: #444; }
.vb-main { flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0; }
.vb-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4.5mm; margin-bottom: 5mm; flex: 0 0 auto; }
.vb-party { border: 1px solid #111; padding: 3mm 3.5mm; min-height: 38mm; }
.vb-party h3 { margin: 0 0 2mm; font-size: 8.5pt; text-transform: uppercase; letter-spacing: .04em; }
.vb-party pre {
  margin: 0 0 2mm; white-space: pre-wrap; font-family: inherit; font-size: 8.5pt; line-height: 1.35;
}
.vb-meta-table { width: 100%; border-collapse: collapse; font-size: 8pt; }
.vb-meta-table td { padding: 0.55mm 0; vertical-align: top; }
.vb-meta-table td:first-child { width: 44%; color: #555; }
.vb-months { margin: 2mm 0 0; font-size: 7.5pt; color: #444; }
.vb-amounts-wrap { flex: 1 1 auto; display: flex; flex-direction: column; }
.portal-vb-table { width: 100%; border-collapse: collapse; font-size: 8.5pt; margin-top: 0; }
.portal-vb-table th, .portal-vb-table td {
  border: 0.6px solid #222; padding: 1.7mm 2.2mm; vertical-align: middle;
}
.portal-vb-table th { background: #f3f4f6; text-align: left; font-weight: 700; }
.portal-vb-table td.num, .portal-vb-table th.num { text-align: right; white-space: nowrap; }
.portal-vb-table tr.vb-deduction td { color: #333; }
.portal-vb-table tr.vb-total td { font-weight: 700; background: #f8fafc; }
.vb-sign {
  margin-top: auto; padding-top: 8mm; display: grid; grid-template-columns: 1fr 1fr; gap: 12mm;
  flex: 0 0 auto;
}
.vb-sign-line {
  border-top: 1px solid #222; padding-top: 1.5mm; font-size: 7pt; color: #555;
}
.vb-footer {
  border-top: 1px solid #111; margin-top: 6mm; padding-top: 2.5mm;
  font-size: 7pt; color: #444; flex: 0 0 auto;
}
.vb-footer p { margin: 0 0 1mm; }
.vb-legal { font-style: italic; }
@media screen {
  .sheet-embed .verdienst-sheet,
  body.sheet-embed .verdienst-sheet {
    height: auto; min-height: 0; max-height: none;
  }
  .sheet-embed .verdienst-document,
  body.sheet-embed .verdienst-document {
    height: auto; min-height: 0;
  }
  .sheet-embed .vb-sign,
  body.sheet-embed .vb-sign { margin-top: 10mm; }
}
"""


def build_verdienst_certificate_html(doc: dict[str, Any] | None, *, meta: dict[str, Any] | None = None) -> str:
    """HTML matching Lohn portal Verdienstbescheinigung print view."""
    d = doc if isinstance(doc, dict) else {}
    m = meta if isinstance(meta, dict) else {}
    year = str(d.get("year") or m.get("year") or (str(d.get("period") or "")[:4]) or "").strip()
    period = str(d.get("period") or m.get("period") or "").strip()[:7]
    period_label = period or "—"
    emp_name = str(d.get("employeeName") or m.get("employeeName") or "").strip()
    emp_addr = str(d.get("employeeAddress") or "").strip()
    emp_block = "\n".join(x for x in (emp_name, emp_addr) if x) or emp_name or "—"
    seller = str(d.get("seller") or m.get("companyName") or "").strip() or "—"
    months = d.get("monthsInYear") if isinstance(d.get("monthsInYear"), list) else []
    months_label = ", ".join(str(x) for x in months) if months else ""
    rows = d.get("rows") if isinstance(d.get("rows"), list) else []
    body_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "")
        cls_parts = []
        if row.get("deduction"):
            cls_parts.append("vb-deduction")
        if "netto" in label.lower():
            cls_parts.append("vb-total")
        cls = f' class="{" ".join(cls_parts)}"' if cls_parts else ""
        body_rows.append(
            f"<tr{cls}><td>{_esc(row.get('label'))}</td>"
            f"<td class=\"num\">{_esc(_amt(row.get('monthly')))}</td>"
            f"<td class=\"num\">{_esc(_amt(row.get('yearly')))}</td></tr>"
        )
    if not body_rows:
        # Fallback from totals if rows missing
        totals = d.get("totals") if isinstance(d.get("totals"), dict) else {}
        ytd = d.get("ytd") if isinstance(d.get("ytd"), dict) else {}
        monthly = d.get("monthly") if isinstance(d.get("monthly"), dict) else {}
        pairs = [
            ("Abrechnungs-Brutto", "gross"),
            ("Steuer-Brutto", "taxGross"),
            ("SV-Brutto", "svGross"),
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
            cls = ' class="vb-total"' if key == "net" else ""
            body_rows.append(
                f"<tr{cls}><td>{_esc(label)}</td>"
                f"<td class=\"num\">{_esc(_amt(mtl))}</td>"
                f"<td class=\"num\">{_esc(_amt(jahr))}</td></tr>"
            )

    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"/><title>Verdienstbescheinigung</title>
<style>{_VB_CSS}</style></head>
<body>
<div class="verdienst-sheet">
  <article class="verdienst-document">
    <header class="vb-header">
      <div class="vb-header-top">
        <div>
          <p class="vb-kicker">WorkPass Lohn · Form VB</p>
          <h2 class="vb-title">Verdienstbescheinigung</h2>
        </div>
        <div class="vb-header-period">
          <span>Bezugsmonat</span>
          <strong>{_esc(period_label)}</strong>
          <em>Jahr {_esc(year or period_label[:4])}</em>
        </div>
      </div>
      <p class="vb-sub">Ausdruck für den Arbeitnehmer · Beträge aus freigegebenen Monatsabrechnungen</p>
    </header>
    <div class="vb-main">
      <div class="vb-grid">
        <section class="vb-party">
          <h3>Arbeitnehmer/in</h3>
          <pre>{_esc(emp_block)}</pre>
          <table class="vb-meta-table">
            <tr><td>Personal-Nr.</td><td>{_esc(d.get("personnelNumber") or d.get("employeeId") or "—")}</td></tr>
            <tr><td>Identifikationsnummer</td><td>{_esc(d.get("employeeTaxId") or "—")}</td></tr>
            <tr><td>SV-Nummer</td><td>{_esc(d.get("employeeInsuranceNo") or "—")}</td></tr>
            <tr><td>Geburtsdatum</td><td>{_esc(d.get("employeeBirthDate") or "—")}</td></tr>
            <tr><td>Steuerklasse</td><td>{_esc(d.get("taxClass") or "—")}</td></tr>
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
      <div class="vb-amounts-wrap">
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
        <div class="vb-sign">
          <div class="vb-sign-line">Ort, Datum</div>
          <div class="vb-sign-line">Unterschrift Arbeitgeber</div>
        </div>
      </div>
    </div>
    <footer class="vb-footer">
      <p>mtl. = Bezugsmonat · Jahr = Summe freigegebener Monate {_esc(year)}</p>
      <p class="vb-legal">Ausdruck für den Arbeitnehmer · nicht Bestandteil der Monatsabrechnung</p>
    </footer>
  </article>
</div>
</body></html>
"""
