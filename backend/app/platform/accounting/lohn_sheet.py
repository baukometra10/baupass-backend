"""Exact WorkPass Lohn DatevSheet A4 HTML (ported from datev-sheet.js print path)."""
from __future__ import annotations

import html
import json
from typing import Any


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _amt(value: Any) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return ""
    sign = "-" if n < 0 else ""
    n = abs(n)
    whole = int(n)
    cents = int(round((n - whole) * 100))
    if cents == 100:
        whole += 1
        cents = 0
    return f"{sign}{whole:,}".replace(",", ".") + f",{cents:02d}"


def _qty(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(n - int(n)) < 1e-9:
        return str(int(n))
    return f"{n:.2f}".replace(".", ",")


def _period_label(period: str) -> str:
    p = (period or "").strip()
    if len(p) >= 7 and p[4] == "-":
        y, m = p[:4], p[5:7]
        names = {
            "01": "Januar",
            "02": "Februar",
            "03": "März",
            "04": "April",
            "05": "Mai",
            "06": "Juni",
            "07": "Juli",
            "08": "August",
            "09": "September",
            "10": "Oktober",
            "11": "November",
            "12": "Dezember",
        }
        return f"für {names.get(m, m)} {y}"
    return p


_CSS = r"""
@page { size: A4 portrait; margin: 0; }
html, body { margin: 0; padding: 0; background: #fff; }
.datev-sheet-a4 {
  width: 210mm !important; height: 297mm !important;
  min-width: 210mm; max-width: 210mm; min-height: 297mm; max-height: 297mm;
  box-sizing: border-box; padding: 5.5mm 7.5mm 4mm;
  background: #fff; color: #151a22;
  font-family: "IBM Plex Mono", "Courier New", Courier, monospace;
  font-size: 7pt; line-height: 1.15;
  display: flex; flex-direction: column; overflow: hidden; flex-shrink: 0;
  justify-content: flex-start; gap: 2.2mm;
}
.ds-zone { display: flex; flex-direction: column; flex-shrink: 0; min-width: 0; }
.ds-zone-wage { gap: 0; flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.ds-zone-pay { gap: 1.4mm; margin-top: auto; }
.ds-brandbar {
  display: flex; justify-content: space-between; align-items: center;
  margin: 0; padding: 0 0 0.85mm; border-bottom: 1.3pt solid #1d4ed8;
}
.ds-brand { font-size: 8.5pt; font-weight: 700; letter-spacing: 0.03em; color: #1e3a5f; display: flex; align-items: center; gap: 2mm; }
.ds-brand span { font-weight: 500; font-size: 6.3pt; color: #5a6a75; margin-left: 2mm; }
.ds-brand-text { display: flex; flex-direction: column; line-height: 1.1; }
.ds-brand-company { font-size: 7.2pt; font-weight: 700; color: #0f172a; }
.ds-brand-product { font-size: 5.6pt; font-weight: 500; color: #5a6a75; }
.ds-mark { font-weight: 700; font-size: 6.5pt; letter-spacing: 0.06em; color: #1e3a5f; }
.ds-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 5mm; margin: 0; }
.ds-title { font-size: 9.5pt; font-weight: 700; letter-spacing: -0.01em; color: #0f172a; }
.ds-title-sub { font-size: 7.2pt; margin-top: 0.35mm; min-height: 2.1mm; color: #334155; }
.ds-meta { text-align: right; font-size: 6.4pt; min-width: 36mm; color: #334155; }
.ds-meta div { margin-bottom: 0.22mm; min-height: 2mm; }
.ds-grid {
  display: grid; grid-template-columns: repeat(8, 1fr); gap: 0;
  border: 0.4pt solid #1a2a33; margin: 0; background: #f8fafc;
}
.ds-cell {
  border-right: 0.2pt solid #b8c2c8; border-bottom: 0.2pt solid #b8c2c8;
  padding: 0.7mm 0.95mm; min-height: 5.3mm; background: #fff;
}
.ds-cell:nth-child(8n) { border-right: none; }
.ds-lab { display: block; font-size: 4.7pt; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; }
.ds-val { display: block; margin-top: 0.25mm; font-size: 6.85pt; min-height: 2.1mm; font-weight: 500; }
.ds-span2 { grid-column: span 2; }
.ds-span3 { grid-column: span 3; }
.ds-mid { display: grid; grid-template-columns: 1.25fr 0.85fr; gap: 1.5mm; margin: 0; }
.ds-box { border: 0.35pt solid #1a2a33; padding: 1.05mm 1.35mm; background: #fff; }
.ds-box h3 {
  margin: 0 0 0.5mm; font-size: 5.3pt; text-transform: uppercase;
  letter-spacing: 0.06em; color: #1e3a5f; font-weight: 700;
  padding-bottom: 0.4mm; border-bottom: 0.25pt solid #d8e0e6;
}
.ds-addr, .ds-hints { white-space: pre-wrap; font-size: 6.65pt; line-height: 1.22; }
.ds-mid-meta { margin-top: 0.7mm; font-size: 6.2pt; color: #475569; }
.ds-wage-wrap { margin: 0; display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; width: 100%; }
.ds-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
.ds-table th, .ds-table td {
  border: 0.25pt solid #9aa8b0; padding: 0.35mm 0.85mm; font-size: 6.55pt; vertical-align: middle;
}
.ds-table th {
  background: #eef3f5; font-size: 5pt; text-transform: uppercase;
  letter-spacing: 0.04em; font-weight: 700; color: #1e3a5f;
}
.ds-num { text-align: right; font-variant-numeric: tabular-nums; }
.ds-flags { text-align: center; font-size: 5.6pt; color: #475569; }
.ds-sum-row td { font-weight: 700; background: #f8fafc; }
.ds-two { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5mm; }
.ds-kv { width: 100%; border-collapse: collapse; }
.ds-kv td { padding: 0.35mm 0; font-size: 6.45pt; }
.ds-kv td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
.ds-net { border: 0.35pt solid #1a2a33; padding: 1.2mm 1.4mm; background: #f8fafc; }
.ds-net-row { display: flex; justify-content: space-between; gap: 2mm; padding: 0.45mm 0; font-size: 6.7pt; }
.ds-net-row strong { font-variant-numeric: tabular-nums; }
.ds-verdienst { margin-top: 1.2mm; }
.ds-foot { display: grid; grid-template-columns: 1.2fr 0.9fr 0.9fr; gap: 1.4mm; align-items: stretch; }
.ds-bank { border: 0.35pt solid #1a2a33; padding: 1.1mm 1.3mm; font-size: 6.5pt; background: #fff; }
.ds-meta-line { margin-top: 0.6mm; color: #334155; }
.ds-ag { width: 100%; border-collapse: collapse; border: 0.35pt solid #1a2a33; }
.ds-ag td { padding: 0.55mm 1mm; font-size: 6.4pt; border-bottom: 0.2pt solid #d8e0e6; }
.ds-ag td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
.ds-pay {
  border: 0.9pt solid #1d4ed8; background: #eff6ff; padding: 1.4mm 1.5mm;
  display: flex; flex-direction: column; justify-content: center; gap: 0.6mm;
}
.ds-pay span { font-size: 5.6pt; text-transform: uppercase; letter-spacing: 0.05em; color: #1e3a5f; }
.ds-pay strong { font-size: 11pt; font-variant-numeric: tabular-nums; color: #0f172a; }
.ds-legal {
  display: grid; grid-template-columns: 1fr auto 1fr; gap: 2mm; align-items: center;
  font-size: 5.2pt; color: #64748b; margin-top: 0.6mm;
}
.ds-legal-center { text-align: center; }
.ds-pad td { color: transparent; }
"""


def payslip_to_sheet_data(payslip: dict[str, Any] | None, *, job: dict[str, Any] | None = None) -> dict[str, Any]:
    p = payslip if isinstance(payslip, dict) else {}
    job = job if isinstance(job, dict) else {}
    t = p.get("totals") if isinstance(p.get("totals"), dict) else {}
    emp = {**(job.get("employee") or {}), **(p.get("employee") or {})}
    co = {**(job.get("company") or {}), **(p.get("company") or {})}
    bank = p.get("bank") if isinstance(p.get("bank"), dict) else {}
    att = p.get("attendance") if isinstance(p.get("attendance"), dict) else {}
    wage_rows = []
    for w in p.get("wageItems") or []:
        if not isinstance(w, dict):
            continue
        code = str(w.get("code") or w.get("lohnart") or "")
        wage_rows.append(
            {
                "code": code,
                "label": str(
                    w.get("label")
                    or w.get("name")
                    or w.get("bezeichnung")
                    or ("Stundenlohn" if code == "STD" else "")
                ),
                "qty": _qty(w.get("quantity") if w.get("quantity") is not None else w.get("menge")),
                "amount": _amt(w.get("amount") if w.get("amount") is not None else w.get("betrag")),
                "taxFlag": str(w.get("taxFlag") or "L"),
                "svFlag": str(w.get("svFlag") or "L"),
            }
        )
    while len(wage_rows) < 5:
        wage_rows.append({"code": "", "label": "", "qty": "", "amount": "", "taxFlag": "", "svFlag": ""})

    gross = t.get("gross")
    net = t.get("net")
    tax_total = float(t.get("payrollTax") or 0) + float(t.get("churchTax") or 0) + float(t.get("solidarity") or 0)
    sv_total = float(t.get("health") or 0) + float(t.get("pension") or 0) + float(t.get("care") or 0) + float(
        t.get("unemployment") or 0
    )
    emp_id = str(emp.get("badgeId") or emp.get("id") or "")
    iban = str(bank.get("iban") or bank.get("IBAN") or "")
    bank_name = str(bank.get("bankName") or bank.get("name") or bank.get("bank") or "")
    period = str(p.get("period") or job.get("period") or "")
    return {
        "companyName": str(co.get("name") or ""),
        "titleMonth": _period_label(period),
        "usa": "USA/US",
        "headDate": str(p.get("releasedAt") or job.get("releasedAt") or "")[:10],
        "headPage": "Blatt 1",
        "persNr": emp_id,
        "birth": str(emp.get("birthDate") or emp.get("dateOfBirth") or ""),
        "stkl": str(emp.get("taxClass") or emp.get("steuerklasse") or ""),
        "konf": str(emp.get("confession") or ""),
        "stTg": str(att.get("days") or att.get("workedDays") or att.get("svDays") or "30"),
        "pgrs": "101",
        "bgrs": "1112",
        "svTg": str(att.get("days") or att.get("svDays") or "30"),
        "svNr": str(emp.get("insuranceNo") or emp.get("svNumber") or ""),
        "kkName": str(emp.get("healthFund") or emp.get("krankenkasse") or ""),
        "kkPct": _qty(emp.get("healthPercent")) if emp.get("healthPercent") is not None else "",
        "workDays": _qty(att.get("days") or att.get("workedDays")),
        "workHours": _qty(att.get("hours") or att.get("totalHours") or att.get("workedHours")),
        "sender": str(co.get("name") or ""),
        "empMeta": f"*Pers.-Nr. {emp_id}*" if emp_id else "",
        "empName": str(emp.get("name") or ""),
        "empAddr": str(emp.get("address") or ""),
        "entry": str(emp.get("entryDate") or emp.get("startDate") or ""),
        "taxIdMid": str(emp.get("taxId") or emp.get("steuerId") or "")[:4],
        "hints": str(p.get("note") or ""),
        "wageRows": wage_rows,
        "grossTotal": _amt(gross),
        "taxTotal": _amt(tax_total),
        "svTotal": _amt(sv_total),
        "netTotal": _amt(net),
        "netVerdienst": _amt(net),
        "payout": _amt(net),
        "stBrutto": _amt(t.get("taxGross") if t.get("taxGross") is not None else gross),
        "lst": _amt(t.get("payrollTax")),
        "kist": _amt(t.get("churchTax")),
        "vbSoli": _amt(t.get("solidarity")),
        "kvB": _amt(t.get("svGross") if t.get("svGross") is not None else gross),
        "kvBeitrag": _amt(t.get("health")),
        "rvBeitrag": _amt(t.get("pension")),
        "avBeitrag": _amt(t.get("unemployment")),
        "pvBeitrag": _amt(t.get("care")),
        "bank": f"Bank {bank_name}" if bank_name else "Bank",
        "konto": f"Konto {iban}" if iban else "Konto",
        "agSv": _amt(t.get("employerShare")),
        "agExtra": _amt(t.get("umlagenTotal")),
        "agTotal": _amt(float(t.get("employerShare") or 0) + float(gross or 0) + float(t.get("umlagenTotal") or 0)),
        "payHint": "Überweisung auf das angegebene Konto",
    }


def _wage_rows_html(rows: list[dict[str, Any]]) -> str:
    out = []
    for r in rows[:8]:
        empty = not (r.get("code") or r.get("label") or r.get("amount"))
        flags = "" if empty else f"{r.get('taxFlag') or 'L'}/{r.get('svFlag') or 'L'}"
        out.append(
            f"<tr class=\"{'ds-pad' if empty else ''}\">"
            f"<td>{_esc(r.get('code') or '')}{'&nbsp;' if empty else ''}</td>"
            f"<td>{_esc(r.get('label') or '')}</td>"
            f"<td class=\"ds-num\">{_esc(r.get('qty') or '')}</td>"
            f"<td class=\"ds-num\">{_esc(r.get('amount') or '')}</td>"
            f"<td class=\"ds-flags\">{_esc(flags)}</td>"
            f"</tr>"
        )
    return "".join(out)


def build_sheet_body_html(data: dict[str, Any]) -> str:
    d = data or {}
    filled = bool(d.get("empName") or d.get("persNr") or d.get("sender") or d.get("grossTotal"))
    brand = (
        f'<div class="ds-brand"><div class="ds-brand-text">'
        f'<span class="ds-brand-company">{_esc(d.get("companyName") or "")}</span>'
        f'<span class="ds-brand-product">WorkPass Lohn</span></div></div>'
        if d.get("companyName")
        else '<div class="ds-brand">WorkPass Lohn<span>Suppix AI</span></div>'
    )
    wage_html = _wage_rows_html(list(d.get("wageRows") or []))
    return f"""
<div class="datev-sheet-a4{' is-empty' if not filled else ''}" id="datevSheetA4">
  <div class="ds-zone ds-zone-head">
    <div class="ds-brandbar">{brand}<div class="ds-mark">Entgeltabrechnung</div></div>
    <div class="ds-head">
      <div>
        <div class="ds-title">Abrechnung der Brutto/Netto-Bezüge</div>
        <div class="ds-title-sub">{_esc(d.get("titleMonth") or "")}</div>
      </div>
      <div class="ds-meta">
        <div>{_esc(d.get("usa") or "")}</div>
        <div>{_esc(d.get("headDate") or "")}</div>
        <div>{_esc(d.get("headPage") or "")}</div>
      </div>
    </div>
  </div>
  <div class="ds-zone ds-zone-master">
    <div class="ds-grid">
      <div class="ds-cell"><span class="ds-lab">Personal-Nr.</span><span class="ds-val">{_esc(d.get("persNr") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">Geburtsdatum</span><span class="ds-val">{_esc(d.get("birth") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">StKl</span><span class="ds-val">{_esc(d.get("stkl") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">Konf</span><span class="ds-val">{_esc(d.get("konf") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">St-Tg</span><span class="ds-val">{_esc(d.get("stTg") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">PGRS</span><span class="ds-val">{_esc(d.get("pgrs") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">BGRS</span><span class="ds-val">{_esc(d.get("bgrs") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">SV-Tg</span><span class="ds-val">{_esc(d.get("svTg") or "")}</span></div>
      <div class="ds-cell ds-span2"><span class="ds-lab">SV-Nummer</span><span class="ds-val">{_esc(d.get("svNr") or "")}</span></div>
      <div class="ds-cell ds-span3"><span class="ds-lab">Krankenkasse</span><span class="ds-val">{_esc(d.get("kkName") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">KK %</span><span class="ds-val">{_esc(d.get("kkPct") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">Arbeitstage</span><span class="ds-val">{_esc(d.get("workDays") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">Stunden</span><span class="ds-val">{_esc(d.get("workHours") or "")}</span></div>
    </div>
    <div class="ds-mid">
      <div class="ds-box">
        <h3>Arbeitgeber / Mitarbeiter</h3>
        <div class="ds-addr">
          <div>{_esc(d.get("sender") or "")}</div>
          <div>{_esc(d.get("empMeta") or "")}</div>
          <div>{_esc(d.get("empName") or "")}</div>
          <div>{_esc(d.get("empAddr") or "")}</div>
          <div class="ds-mid-meta">Eintritt: {_esc(d.get("entry") or "")} · Steuer-ID: {_esc(d.get("taxIdMid") or "")}</div>
        </div>
      </div>
      <div class="ds-box">
        <h3>Hinweise zur Abrechnung</h3>
        <div class="ds-hints">{_esc(d.get("hints") or "")}</div>
      </div>
    </div>
  </div>
  <div class="ds-zone ds-zone-wage">
    <div class="ds-wage-wrap">
      <table class="ds-table">
        <thead><tr><th>Lohnart</th><th>Bezeichnung</th><th class="ds-num">Anzahl</th><th class="ds-num">Betrag</th><th>St/SV</th></tr></thead>
        <tbody>{wage_html}</tbody>
        <tfoot><tr class="ds-sum-row"><td colspan="3">Gesamt-Brutto</td><td class="ds-num">{_esc(d.get("grossTotal") or "")}</td><td></td></tr></tfoot>
      </table>
    </div>
  </div>
  <div class="ds-zone ds-zone-calc">
    <div class="ds-two">
      <div class="ds-box">
        <h3>Steuer / Sozialversicherung</h3>
        <table class="ds-kv">
          <tr><td>Steuer-Brutto</td><td>{_esc(d.get("stBrutto") or "")}</td></tr>
          <tr><td>Lohnsteuer</td><td>{_esc(d.get("lst") or "")}</td></tr>
          <tr><td>Kirchensteuer</td><td>{_esc(d.get("kist") or "")}</td></tr>
          <tr><td>Solidaritätszuschlag</td><td>{_esc(d.get("vbSoli") or "")}</td></tr>
          <tr><td>KV-/RV-Brutto</td><td>{_esc(d.get("kvB") or "")}</td></tr>
          <tr><td>KV-Beitrag</td><td>{_esc(d.get("kvBeitrag") or "")}</td></tr>
          <tr><td>RV-Beitrag</td><td>{_esc(d.get("rvBeitrag") or "")}</td></tr>
          <tr><td>AV-Beitrag</td><td>{_esc(d.get("avBeitrag") or "")}</td></tr>
          <tr><td>PV-Beitrag</td><td>{_esc(d.get("pvBeitrag") or "")}</td></tr>
        </table>
      </div>
      <div class="ds-net">
        <div class="ds-net-row"><span>Steuerabzüge</span><strong>{_esc(d.get("taxTotal") or "")}</strong></div>
        <div class="ds-net-row"><span>SV-Abzüge</span><strong>{_esc(d.get("svTotal") or "")}</strong></div>
        <div class="ds-net-row"><span>Netto-Verdienst</span><strong>{_esc(d.get("netVerdienst") or d.get("netTotal") or "")}</strong></div>
      </div>
    </div>
  </div>
  <div class="ds-zone ds-zone-pay">
    <div class="ds-foot">
      <div class="ds-bank">
        <div>{_esc(d.get("bank") or "")}</div>
        <div>{_esc(d.get("konto") or "")}</div>
        <div class="ds-meta-line"><strong>Zahlungsweg:</strong> {_esc(d.get("payHint") or "")}</div>
      </div>
      <table class="ds-ag">
        <tr><td>SV-AG-Anteil</td><td>{_esc(d.get("agSv") or "")}</td></tr>
        <tr><td>Zus. AG-Kosten</td><td>{_esc(d.get("agExtra") or "")}</td></tr>
        <tr><td>Gesamtkosten</td><td>{_esc(d.get("agTotal") or "")}</td></tr>
      </table>
      <div class="ds-pay"><span>Auszahlungsbetrag</span><strong>{_esc(d.get("payout") or "")}</strong></div>
    </div>
    <div class="ds-legal">
      <div>WorkPass Lohn · Form LOHN</div>
      <div class="ds-legal-center">– Entgeltbescheinigung nach § 108 Abs. 3 Satz 1 GewO –</div>
      <div class="ds-mark">Suppix AI</div>
    </div>
  </div>
</div>
""".strip()


def build_payslip_print_html(payslip: dict[str, Any] | None, *, job: dict[str, Any] | None = None) -> str:
    data = payslip_to_sheet_data(payslip, job=job)
    body = build_sheet_body_html(data)
    period = str((payslip or {}).get("period") or (job or {}).get("period") or "")
    return f"""<!DOCTYPE html>
<html lang="de"><head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Entgeltabrechnung {_esc(period)}</title>
<style>{_CSS}</style>
</head>
<body style="margin:0;background:#e8edf2;display:flex;justify-content:center;padding:12px;">
{body}
</body></html>"""


def payslip_document_from_meta(meta: Any) -> dict[str, Any] | None:
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            return None
    if not isinstance(meta, dict):
        return None
    doc = meta.get("document")
    return doc if isinstance(doc, dict) else None
