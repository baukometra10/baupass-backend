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


# Exact CSS from WorkPass Lohn datev-sheet.js (print path).
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
  display: flex; flex-direction: column; overflow: hidden;
  flex-shrink: 0; justify-content: flex-start; gap: 2.2mm;
}
.datev-sheet-a4.is-empty .ds-val:empty::after,
.datev-sheet-a4.is-empty .ds-hints:empty::after,
.datev-sheet-a4.is-empty #dsv_sender:empty::after,
.datev-sheet-a4.is-empty #dsv_empName:empty::after {
  content: ""; display: block; min-height: 2mm; border-bottom: 0.35pt dotted #c5ced4;
}
.datev-sheet-a4.is-empty .ds-pay { opacity: 0.55; }
.ds-zone { display: flex; flex-direction: column; flex-shrink: 0; min-width: 0; }
.ds-zone-head { gap: 1.2mm; }
.ds-zone-master { gap: 1.6mm; }
.ds-zone-wage { gap: 0; flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.ds-zone-calc { gap: 1.6mm; }
.ds-zone-pay { gap: 1.4mm; margin-top: auto; }
.ds-brandbar {
  display: flex; justify-content: space-between; align-items: center;
  margin: 0; padding: 0 0 0.85mm; border-bottom: 1.3pt solid #1d4ed8;
}
.ds-brand { font-size: 8.5pt; font-weight: 700; letter-spacing: 0.03em; color: #1e3a5f; display: flex; align-items: center; gap: 2mm; }
.ds-brand span { font-weight: 500; font-size: 6.3pt; color: #5a6a75; margin-left: 2mm; }
.ds-brand-logo { max-height: 7.5mm; max-width: 28mm; width: auto; height: auto; object-fit: contain; display: block; }
.ds-brand-text { display: flex; flex-direction: column; line-height: 1.1; }
.ds-brand-company { font-size: 7.2pt; font-weight: 700; color: #0f172a; }
.ds-brand-product { font-size: 5.6pt; font-weight: 500; color: #5a6a75; }
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
.ds-mid-meta { margin-top: 0.7mm; font-size: 6.2pt; color: #475569; }
.ds-span2 { grid-column: span 2; }
.ds-span3 { grid-column: span 3; }
.ds-mid { display: grid; grid-template-columns: 1.25fr 0.85fr; gap: 1.5mm; margin: 0; align-items: stretch; }
.ds-mid > .ds-box { display: flex; flex-direction: column; min-height: 20mm; }
.ds-mid .ds-addr, .ds-mid .ds-hints { flex: 1 1 auto; }
.ds-box { border: 0.35pt solid #1a2a33; padding: 1.05mm 1.35mm; background: #fff; }
.ds-box h3 {
  margin: 0 0 0.5mm; font-size: 5.3pt; text-transform: uppercase;
  letter-spacing: 0.06em; color: #1e3a5f; font-weight: 700;
  padding-bottom: 0.4mm; border-bottom: 0.25pt solid #d8e0e6;
}
.ds-addr { white-space: pre-wrap; font-size: 6.65pt; line-height: 1.22; min-height: 0; }
.ds-hints { white-space: pre-wrap; font-size: 6.45pt; line-height: 1.22; min-height: 0; }
.ds-wage-wrap { margin: 0; display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; width: 100%; }
.ds-table { width: 100%; border-collapse: collapse; table-layout: fixed; flex: 1 1 auto; height: 100%; }
.ds-table th, .ds-table td {
  border: 0.25pt solid #9aa8b0; padding: 0.35mm 0.85mm; font-size: 6.55pt; vertical-align: middle;
}
.ds-table th {
  background: #eef3f5; font-size: 5pt; text-transform: uppercase;
  letter-spacing: 0.04em; font-weight: 700; color: #1e3a5f;
}
.ds-table col.ds-col-code { width: 10%; }
.ds-table col.ds-col-label { width: 40%; }
.ds-table col.ds-col-qty { width: 16%; }
.ds-table col.ds-col-amount { width: 22%; }
.ds-table col.ds-col-flags { width: 12%; }
.ds-table td:nth-child(2) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ds-table tbody tr { height: 3.9mm; }
.ds-table tbody tr.ds-pad td { color: transparent; border-color: #cfd8de; background: #fafbfc; }
.ds-num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.ds-flags { text-align: center; font-size: 6.1pt; color: #333; }
.ds-sum-row td { font-weight: 700; background: #f1f5f7; border-top: 0.8pt solid #1a2a33; height: 4.2mm; }
.ds-two { display: grid; grid-template-columns: 1.2fr 0.9fr; gap: 1.5mm; margin: 0; align-items: stretch; }
.ds-kv { width: 100%; border-collapse: collapse; }
.ds-kv td { padding: 0.5mm 0; font-size: 6.55pt; border-bottom: 0.15pt solid #e2e8eb; }
.ds-kv td:last-child { text-align: right; font-variant-numeric: tabular-nums; width: 22mm; }
.ds-kv tr:last-child td { border-bottom: none; }
.ds-net {
  border: 0.8pt solid #1e3a5f; padding: 1.7mm 1.7mm; background: #f3f8f9;
  display: flex; flex-direction: column; justify-content: center; gap: 1.2mm;
}
.ds-net-row { display: flex; justify-content: space-between; align-items: baseline; gap: 3mm; }
.ds-net-row span { font-size: 6.4pt; color: #334155; }
.ds-net-row strong { font-size: 8.2pt; color: #1e3a5f; }
.ds-net-method { margin-top: 1.5mm; font-size: 5.8pt; color: #64748b; }
.ds-verdienst { margin: 0; }
.ds-verdienst .ds-two { margin: 0; gap: 3mm; }
.ds-foot {
  display: grid; grid-template-columns: 1.2fr 0.85fr 0.95fr;
  gap: 1.6mm; align-items: stretch; border-top: 0.7pt solid #1a2a33;
  padding-top: 1.5mm; margin: 0;
}
.ds-bank { font-size: 6.45pt; line-height: 1.28; }
.ds-bank .ds-meta-line { margin-top: 0.5mm; color: #334155; }
.ds-bank .ds-meta-line strong { color: #1e3a5f; }
.ds-ag { width: 100%; border-collapse: collapse; align-self: center; }
.ds-ag td { padding: 0.5mm 0; font-size: 6.55pt; }
.ds-ag td:last-child { text-align: right; width: 20mm; }
.ds-pay {
  border: 1pt solid #1d4ed8; padding: 1.8mm 1.9mm;
  background: linear-gradient(165deg, #1e3a5f 0%, #152a45 100%);
  color: #fff; display: flex; flex-direction: column; justify-content: center; gap: 0.7mm;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.12);
}
.ds-pay span { font-size: 5.3pt; text-transform: uppercase; letter-spacing: 0.07em; opacity: 0.88; }
.ds-pay strong { font-size: 11.5pt; text-align: right; min-height: 4.2mm; letter-spacing: 0.01em; }
.ds-legal {
  margin: 0; padding-top: 0.7mm; display: flex; justify-content: space-between; align-items: end;
  gap: 3mm; font-size: 5pt; color: #5a6a75; border-top: 0.3pt solid #c5ced4;
}
.ds-legal-center { text-align: center; flex: 1; }
.ds-mark { font-weight: 700; font-size: 6.5pt; letter-spacing: 0.06em; color: #1e3a5f; }
body.sheet-chrome {
  margin: 0; min-height: 100vh; box-sizing: border-box;
  display: flex; justify-content: center; align-items: flex-start;
  padding: 16px; overflow: auto;
}
body.sheet-chrome.theme-light { background: #e8edf2; }
body.sheet-chrome.theme-dark { background: #0b1220; }
"""


def _clean_sheet_hint(note: Any) -> str:
    """Drop internal platform/Lohn debug notes from the visible Hinweise box."""
    text = str(note or "").strip()
    if not text:
        return ""
    low = text.lower()
    junk = (
        "grossestimate",
        "platform hint",
        "brutto when hourly",
        "computes official payroll",
        "bruttohint",
    )
    if any(token in low for token in junk):
        return ""
    return text


def _first_filled(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _digits_only(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _tax_id_display(*values: Any) -> str:
    """Full Steuer-ID (11 digits); never truncate to the DATEV 4-digit preview."""
    return _first_filled(*values)


def enrich_payslip_with_master(
    payslip: dict[str, Any] | None,
    master: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fill empty Stammdaten gaps (Krankenkasse, StKl, SV-Nr, …) from platform master."""
    out = dict(payslip or {})
    master = master if isinstance(master, dict) else {}
    if not master:
        return out
    emp = dict(out.get("employee") if isinstance(out.get("employee"), dict) else {})
    bank = dict(out.get("bank") if isinstance(out.get("bank"), dict) else {})
    co = dict(out.get("company") if isinstance(out.get("company"), dict) else {})

    def fill_emp(*keys: str, sources: list[Any]) -> None:
        for key in keys:
            if _first_filled(emp.get(key)):
                return
        value = _first_filled(*sources)
        if not value:
            return
        for key in keys:
            emp[key] = value

    fill_emp("name", sources=[master.get("name")])
    fill_emp("badgeId", "id", sources=[master.get("badgeId"), master.get("personnelNumber"), master.get("id")])
    fill_emp(
        "birthDate",
        "dateOfBirth",
        sources=[master.get("birthDate"), master.get("dateOfBirth")],
    )
    fill_emp(
        "taxClass",
        "steuerklasse",
        sources=[master.get("taxClass"), master.get("steuerklasse")],
    )
    fill_emp("confession", sources=[master.get("confession"), master.get("konfession")])
    fill_emp(
        "insuranceNo",
        "svNumber",
        "insuranceNumber",
        sources=[
            master.get("insuranceNo"),
            master.get("insuranceNumber"),
            master.get("svNumber"),
        ],
    )
    fill_emp(
        "healthFund",
        "krankenkasse",
        "healthInsurance",
        sources=[
            master.get("healthFund"),
            master.get("krankenkasse"),
            master.get("healthInsurance"),
        ],
    )
    if emp.get("healthPercent") in (None, "") and master.get("healthPercent") not in (None, ""):
        emp["healthPercent"] = master.get("healthPercent")
    fill_emp("address", sources=[master.get("address"), master.get("homeAddress")])
    fill_emp(
        "entryDate",
        "startDate",
        sources=[master.get("entryDate"), master.get("startDate")],
    )
    fill_emp("taxId", "steuerId", sources=[master.get("taxId"), master.get("steuerId")])

    if not _first_filled(bank.get("iban"), bank.get("IBAN")):
        iban = _first_filled(master.get("iban"), (master.get("bank") or {}).get("iban") if isinstance(master.get("bank"), dict) else "")
        if iban:
            bank["iban"] = iban
    if not _first_filled(bank.get("bankName"), bank.get("name"), bank.get("bank")):
        bname = _first_filled(
            master.get("bankName"),
            (master.get("bank") or {}).get("name") if isinstance(master.get("bank"), dict) else "",
        )
        if bname:
            bank["bankName"] = bname
    if not _first_filled(co.get("name")):
        cname = _first_filled(master.get("companyName"), (master.get("company") or {}).get("name") if isinstance(master.get("company"), dict) else "")
        if cname:
            co["name"] = cname

    out["employee"] = emp
    if bank:
        out["bank"] = bank
    if co:
        out["company"] = co
    out["note"] = _clean_sheet_hint(out.get("note"))
    out["footerNote"] = _clean_sheet_hint(out.get("footerNote"))
    return out


def snapshot_stammdaten(sheet_data: dict[str, Any] | None, payslip: dict[str, Any] | None) -> dict[str, Any]:
    """Frozen Stammdaten copied onto the statement so later Lohn/master edits cannot change a sent slip."""
    d = sheet_data if isinstance(sheet_data, dict) else {}
    emp = (payslip or {}).get("employee") if isinstance((payslip or {}).get("employee"), dict) else {}
    return {
        "healthFund": _first_filled(d.get("kkName"), emp.get("healthFund"), emp.get("krankenkasse")),
        "healthPercent": _first_filled(d.get("kkPct"), emp.get("healthPercent")),
        "taxId": _first_filled(d.get("taxIdMid"), emp.get("taxId"), emp.get("steuerId")),
        "personnelNumber": _first_filled(d.get("persNr"), emp.get("personnelNumber")),
        "birthDate": _first_filled(d.get("birth"), emp.get("birthDate")),
        "taxClass": _first_filled(d.get("stkl"), emp.get("taxClass")),
        "insuranceNo": _first_filled(d.get("svNr"), emp.get("insuranceNo")),
        "name": _first_filled(d.get("empName"), emp.get("name")),
        "address": _first_filled(d.get("empAddr"), emp.get("address")),
        "krankenkasse": _first_filled(d.get("kkName"), emp.get("healthFund")),
        "steuerId": _first_filled(d.get("taxIdMid"), emp.get("taxId")),
    }


def overlay_stammdaten(
    payslip: dict[str, Any] | None,
    lock: dict[str, Any] | None,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Apply locked Stammdaten. overwrite=True after release (lock wins)."""
    out = dict(payslip or {})
    lock = lock if isinstance(lock, dict) else {}
    if not lock:
        return out
    if overwrite:
        emp = dict(out.get("employee") if isinstance(out.get("employee"), dict) else {})
        mapping = {
            "healthFund": lock.get("healthFund") or lock.get("krankenkasse"),
            "krankenkasse": lock.get("healthFund") or lock.get("krankenkasse"),
            "healthInsurance": lock.get("healthFund") or lock.get("krankenkasse"),
            "healthPercent": lock.get("healthPercent"),
            "taxId": lock.get("taxId") or lock.get("steuerId"),
            "steuerId": lock.get("taxId") or lock.get("steuerId"),
            "personnelNumber": lock.get("personnelNumber"),
            "birthDate": lock.get("birthDate"),
            "taxClass": lock.get("taxClass"),
            "insuranceNo": lock.get("insuranceNo"),
            "name": lock.get("name"),
            "address": lock.get("address"),
        }
        for key, value in mapping.items():
            if _first_filled(value):
                emp[key] = value
        out["employee"] = emp
        return out
    return enrich_payslip_with_master(out, lock)


def stammdaten_warnings(sheet_data: dict[str, Any] | None, live: dict[str, Any] | None) -> list[str]:
    """Warn when the sheet value differs from current employee master (before send)."""
    d = sheet_data if isinstance(sheet_data, dict) else {}
    live = live if isinstance(live, dict) else {}
    checks = [
        ("Krankenkasse", d.get("kkName"), live.get("healthFund") or live.get("krankenkasse")),
        ("Steuer-ID", d.get("taxIdMid"), live.get("taxId") or live.get("steuerId")),
        ("Personal-Nr.", d.get("persNr"), live.get("personnelNumber") or live.get("personalnummer")),
    ]
    out: list[str] = []
    for label, sheet_val, live_val in checks:
        a = _first_filled(sheet_val)
        b = _first_filled(live_val)
        if not a or not b:
            continue
        a_key = _digits_only(a) or a.lower()
        b_key = _digits_only(b) or b.lower()
        if a_key != b_key:
            out.append(f"{label}: Abrechnung «{a}» ≠ Stammdaten «{b}»")
    return out


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
    emp_id_raw = _first_filled(emp.get("id"), emp.get("employeeId"))
    badge_id = _first_filled(emp.get("badgeId"), emp.get("badge"))
    personnel_number = _first_filled(
        emp.get("personnelNumber"),
        emp.get("personalnummer"),
        emp.get("personnelNo"),
        emp.get("persNrDisplay"),
    )
    # Same rule as Lohn payroll-core.js: never print badge; use Pers.-Nr.
    if personnel_number:
        print_pers_nr = personnel_number
    elif badge_id and emp_id_raw and badge_id == emp_id_raw:
        print_pers_nr = ""
    elif emp_id_raw and emp_id_raw != badge_id:
        print_pers_nr = emp_id_raw
    else:
        print_pers_nr = ""
    iban = str(bank.get("iban") or bank.get("IBAN") or "")
    bank_name = str(bank.get("bankName") or bank.get("name") or bank.get("bank") or "")
    period = str(p.get("period") or job.get("period") or "")
    rates = p.get("rates") if isinstance(p.get("rates"), dict) else {}
    if not rates and isinstance(t.get("rates"), dict):
        rates = t.get("rates") or {}
    health_fund = _first_filled(emp.get("healthFund"), emp.get("krankenkasse"), emp.get("healthInsurance"))
    kk_pct_src = _first_filled(
        emp.get("healthPercent"),
        emp.get("kkPercent"),
        emp.get("kkPct"),
        emp.get("krankenkassePercent"),
        emp.get("zusatzbeitrag"),
        emp.get("additionalContribution"),
        rates.get("healthPercent"),
        rates.get("kkPercent"),
        rates.get("kkPct"),
        rates.get("zusatzbeitrag"),
        rates.get("additionalContribution"),
        p.get("healthPercent"),
    )
    if not kk_pct_src and (health_fund or any(r.get("code") or r.get("amount") for r in wage_rows)):
        try:
            add = float(str(emp.get("healthAdditionalPercent") or "2.9").replace(",", "."))
        except (TypeError, ValueError):
            add = 2.9
        kk_pct_src = 7.3 + (add / 2.0)
    tax_class_raw = str(emp.get("taxClass") or emp.get("steuerklasse") or "").strip()
    tax_class_map = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6"}
    stkl = tax_class_map.get(tax_class_raw) or "".join(ch for ch in tax_class_raw if ch.isdigit())
    days = att.get("days")
    if days in (None, ""):
        days = att.get("workedDays")
    if days in (None, ""):
        days = att.get("svDays")
    hours = att.get("hours")
    if hours in (None, ""):
        hours = att.get("totalHours")
    if hours in (None, ""):
        hours = att.get("workedHours")
    return {
        "companyName": str(co.get("name") or ""),
        "titleMonth": _period_label(period),
        "usa": "USA/US",
        "headDate": str(p.get("releasedAt") or job.get("releasedAt") or "")[:10],
        "headPage": "Blatt: 1",
        "persNr": print_pers_nr,
        "birth": str(emp.get("birthDate") or emp.get("dateOfBirth") or ""),
        "stkl": stkl,
        "konf": str(emp.get("confession") or emp.get("konfession") or ""),
        "stTg": "" if days in (None, "") else str(days),
        "pgrs": _first_filled(emp.get("personengruppe"), emp.get("pgrs")) or "101",
        "bgrs": _first_filled(emp.get("beitragsgruppe"), emp.get("bgrs")) or "1111",
        "svTg": "" if days in (None, "") else str(days),
        "svNr": str(emp.get("insuranceNo") or emp.get("svNumber") or emp.get("insuranceNumber") or ""),
        "kkName": health_fund,
        "kkPct": _qty(kk_pct_src) if kk_pct_src not in (None, "") else "",
        "workDays": _qty(days),
        "workHours": _qty(hours),
        "sender": str(co.get("name") or ""),
        "empMeta": f"*Pers.-Nr. {print_pers_nr}*" if print_pers_nr else "",
        "empName": str(emp.get("name") or ""),
        "empAddr": str(emp.get("address") or ""),
        "entry": str(emp.get("entryDate") or emp.get("startDate") or ""),
        "taxIdMid": _tax_id_display(emp.get("taxId"), emp.get("steuerId")),
        "hints": str(p.get("note") or ""),
        "wageRows": wage_rows,
        "grossTotal": _amt(gross),
        "taxTotal": _amt(tax_total),
        "svTotal": _amt(sv_total),
        "netAbzug": _amt(t.get("netDeductions") or t.get("otherNetDeductions") or 0),
        "netTotal": _amt(net),
        "netVerdienst": _amt(net),
        "payout": _amt(net),
        "stBrutto": _amt(t.get("taxGross") if t.get("taxGross") is not None else gross),
        "lst": _amt(t.get("payrollTax")),
        "kist": _amt(t.get("churchTax")),
        "vbSoli": _amt(t.get("solidarity")),
        "vbGross": _amt(gross),
        "vbTaxGross": _amt(t.get("taxGross") if t.get("taxGross") is not None else gross),
        "vbLst": _amt(t.get("payrollTax")),
        "vbKist": _amt(t.get("churchTax")),
        "vbSvGross": _amt(t.get("svGross") if t.get("svGross") is not None else gross),
        "vbKv": _amt(t.get("health")),
        "vbRv": _amt(t.get("pension")),
        "vbAv": _amt(t.get("unemployment")),
        "vbPv": _amt(t.get("care")),
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
        "footerNote": str(p.get("footerNote") or ""),
        "calcMethod": str(t.get("calcMethod") or ""),
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
    filled = bool(
        d.get("empName")
        or d.get("persNr")
        or d.get("sender")
        or d.get("grossTotal")
        or any((r.get("code") or r.get("label") or r.get("amount")) for r in (d.get("wageRows") or []) if isinstance(r, dict))
    )
    logo = str(d.get("logoDataUrl") or d.get("logoUrl") or "").strip()
    brand_company = str(d.get("companyName") or "").strip()
    if logo or brand_company:
        logo_html = f'<img class="ds-brand-logo" src="{_esc(logo)}" alt="" />' if logo else ""
        company_html = (
            f'<span class="ds-brand-company">{_esc(brand_company)}</span>' if brand_company else ""
        )
        brand = (
            f'<div class="ds-brand">{logo_html}'
            f'<div class="ds-brand-text">{company_html}'
            f'<span class="ds-brand-product">WorkPass Lohn</span></div></div>'
        )
    else:
        brand = '<div class="ds-brand">WorkPass Lohn<span>Suppix AI</span></div>'
    mid_meta = (
        f'Eintritt: <span id="dsv_entry">{_esc(d.get("entry") or "")}</span>'
        f' · Steuer-ID: <span id="dsv_taxIdMid">{_esc(d.get("taxIdMid") or "")}</span>'
        if filled
        else '<span id="dsv_entry" hidden></span><span id="dsv_taxIdMid" hidden></span>'
    )
    pay_hint = (d.get("payHint") or "Überweisung auf das angegebene Konto") if filled else ""
    footer_note = (d.get("footerNote") or d.get("hints") or "") if filled else ""
    wage_html = _wage_rows_html(list(d.get("wageRows") or []))
    calc_method = (
        f'<div class="ds-net-method">{_esc(d.get("calcMethod") or "")}</div>' if d.get("calcMethod") else ""
    )
    footer_note_html = (
        f'<div class="ds-meta-line"><strong>Bemerkung:</strong> <span id="dsv_footerNote">{_esc(footer_note)}</span></div>'
        if footer_note
        else '<span id="dsv_footerNote" hidden></span>'
    )
    return f"""
<div class="datev-sheet-a4{' is-empty' if not filled else ''}" id="datevSheetA4" data-filled="{'1' if filled else '0'}">
  <div class="ds-zone ds-zone-head">
    <div class="ds-brandbar">{brand}<div class="ds-mark">Entgeltabrechnung</div></div>
    <div class="ds-head">
      <div>
        <div class="ds-title">Abrechnung der Brutto/Netto-Bezüge</div>
        <div class="ds-title-sub" id="dsv_titleMonth">{_esc(d.get("titleMonth") or "")}</div>
      </div>
      <div class="ds-meta">
        <div id="dsv_usa">{_esc(d.get("usa") or "")}</div>
        <div id="dsv_headDate">{_esc(d.get("headDate") or "")}</div>
        <div id="dsv_headPage">{_esc(d.get("headPage") or "")}</div>
      </div>
    </div>
  </div>
  <div class="ds-zone ds-zone-master">
    <div class="ds-grid">
      <div class="ds-cell"><span class="ds-lab">Personal-Nr.</span><span class="ds-val" id="dsv_persNr">{_esc(d.get("persNr") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">Geburtsdatum</span><span class="ds-val" id="dsv_birth">{_esc(d.get("birth") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">StKl</span><span class="ds-val" id="dsv_stkl">{_esc(d.get("stkl") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">Konf</span><span class="ds-val" id="dsv_konf">{_esc(d.get("konf") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">St-Tg</span><span class="ds-val" id="dsv_stTg">{_esc(d.get("stTg") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">PGRS</span><span class="ds-val" id="dsv_pgrs">{_esc(d.get("pgrs") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">BGRS</span><span class="ds-val" id="dsv_bgrs">{_esc(d.get("bgrs") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">SV-Tg</span><span class="ds-val" id="dsv_svTg">{_esc(d.get("svTg") or "")}</span></div>
      <div class="ds-cell ds-span2"><span class="ds-lab">SV-Nummer</span><span class="ds-val" id="dsv_svNr">{_esc(d.get("svNr") or "")}</span></div>
      <div class="ds-cell ds-span3"><span class="ds-lab">Krankenkasse</span><span class="ds-val" id="dsv_kkName">{_esc(d.get("kkName") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">KK %</span><span class="ds-val" id="dsv_kkPct">{_esc(d.get("kkPct") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">Arbeitstage</span><span class="ds-val" id="dsv_workDays">{_esc(d.get("workDays") or "")}</span></div>
      <div class="ds-cell"><span class="ds-lab">Stunden</span><span class="ds-val" id="dsv_workHours">{_esc(d.get("workHours") or "")}</span></div>
    </div>
    <div class="ds-mid">
      <div class="ds-box">
        <h3>Arbeitgeber / Mitarbeiter</h3>
        <div class="ds-addr">
          <div id="dsv_sender">{_esc(d.get("sender") or "")}</div>
          <div id="dsv_empMeta">{_esc(d.get("empMeta") or "")}</div>
          <div id="dsv_empName">{_esc(d.get("empName") or "")}</div>
          <div id="dsv_empAddr">{_esc(d.get("empAddr") or "")}</div>
          <div class="ds-mid-meta">{mid_meta}</div>
        </div>
      </div>
      <div class="ds-box">
        <h3>Hinweise zur Abrechnung</h3>
        <div class="ds-hints" id="dsv_hints">{_esc(d.get("hints") or "")}</div>
      </div>
    </div>
  </div>
  <div class="ds-zone ds-zone-wage">
    <div class="ds-wage-wrap">
      <table class="ds-table">
        <colgroup>
          <col class="ds-col-code" /><col class="ds-col-label" /><col class="ds-col-qty" />
          <col class="ds-col-amount" /><col class="ds-col-flags" />
        </colgroup>
        <thead>
          <tr>
            <th>Lohnart</th><th>Bezeichnung</th><th class="ds-num">Anzahl</th>
            <th class="ds-num">Betrag</th><th>St/SV</th>
          </tr>
        </thead>
        <tbody id="datevWageRows">{wage_html}</tbody>
        <tfoot>
          <tr class="ds-sum-row">
            <td colspan="3">Gesamt-Brutto</td>
            <td class="ds-num" id="dsv_grossTotal">{_esc(d.get("grossTotal") or "")}</td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>
  </div>
  <div class="ds-zone ds-zone-calc">
    <div class="ds-two">
      <div class="ds-box">
        <h3>Steuer / Sozialversicherung</h3>
        <table class="ds-kv">
          <tr><td>Steuer-Brutto</td><td id="dsv_stBrutto">{_esc(d.get("stBrutto") or "")}</td></tr>
          <tr><td>Lohnsteuer</td><td id="dsv_lst">{_esc(d.get("lst") or "")}</td></tr>
          <tr><td>Kirchensteuer</td><td id="dsv_kist">{_esc(d.get("kist") or "")}</td></tr>
          <tr><td>Solidaritätszuschlag</td><td id="dsv_soliMini">{_esc(d.get("vbSoli") or "")}</td></tr>
          <tr><td>KV-/RV-Brutto</td><td id="dsv_kvB">{_esc(d.get("kvB") or "")}</td></tr>
          <tr><td>KV-Beitrag</td><td id="dsv_kvBeitrag">{_esc(d.get("kvBeitrag") or "")}</td></tr>
          <tr><td>RV-Beitrag</td><td id="dsv_rvBeitrag">{_esc(d.get("rvBeitrag") or "")}</td></tr>
          <tr><td>AV-Beitrag</td><td id="dsv_avBeitrag">{_esc(d.get("avBeitrag") or "")}</td></tr>
          <tr><td>PV-Beitrag</td><td id="dsv_pvBeitrag">{_esc(d.get("pvBeitrag") or "")}</td></tr>
        </table>
      </div>
      <div class="ds-net">
        <div class="ds-net-row"><span>Steuerabzüge</span><strong id="dsv_taxTotal">{_esc(d.get("taxTotal") or "")}</strong></div>
        <div class="ds-net-row"><span>SV-Abzüge</span><strong id="dsv_svTotal">{_esc(d.get("svTotal") or "")}</strong></div>
        <div class="ds-net-row"><span>Sonst. Netto-Abzüge</span><strong id="dsv_netAbzug">{_esc(d.get("netAbzug") or "")}</strong></div>
        <div class="ds-net-row"><span>Netto-Verdienst</span><strong id="dsv_netVerdienst">{_esc(d.get("netVerdienst") or d.get("netTotal") or "")}</strong></div>
        {calc_method}
      </div>
    </div>
    <div class="ds-box ds-verdienst">
      <h3>Verdienstbescheinigung</h3>
      <div class="ds-two">
        <table class="ds-kv">
          <tr><td>Gesamt-Brutto</td><td id="dsv_vbGross">{_esc(d.get("vbGross") or d.get("grossTotal") or "")}</td></tr>
          <tr><td>Steuer-Brutto</td><td id="dsv_vbTaxGross">{_esc(d.get("vbTaxGross") or d.get("stBrutto") or "")}</td></tr>
          <tr><td>Lohnsteuer</td><td id="dsv_vbLst">{_esc(d.get("vbLst") or d.get("lst") or "")}</td></tr>
          <tr><td>Kirchensteuer</td><td id="dsv_vbKist">{_esc(d.get("vbKist") or d.get("kist") or "")}</td></tr>
          <tr><td>Solidaritätszuschlag</td><td id="dsv_vbSoli">{_esc(d.get("vbSoli") or "")}</td></tr>
        </table>
        <table class="ds-kv">
          <tr><td>SV-Brutto</td><td id="dsv_vbSvGross">{_esc(d.get("vbSvGross") or d.get("kvB") or "")}</td></tr>
          <tr><td>KV-Beitrag</td><td id="dsv_vbKv">{_esc(d.get("vbKv") or d.get("kvBeitrag") or "")}</td></tr>
          <tr><td>RV-Beitrag</td><td id="dsv_vbRv">{_esc(d.get("vbRv") or d.get("rvBeitrag") or "")}</td></tr>
          <tr><td>AV-Beitrag</td><td id="dsv_vbAv">{_esc(d.get("vbAv") or d.get("avBeitrag") or "")}</td></tr>
          <tr><td>PV-Beitrag</td><td id="dsv_vbPv">{_esc(d.get("vbPv") or d.get("pvBeitrag") or "")}</td></tr>
        </table>
      </div>
    </div>
  </div>
  <div class="ds-zone ds-zone-pay">
    <div class="ds-foot">
      <div class="ds-bank">
        <div id="dsv_bank">{_esc(d.get("bank") or "")}</div>
        <div id="dsv_konto">{_esc(d.get("konto") or "")}</div>
        <div class="ds-meta-line"><strong>Zahlungsweg:</strong> <span id="dsv_payHint">{_esc(pay_hint)}</span></div>
        {footer_note_html}
      </div>
      <table class="ds-ag">
        <tr><td>SV-AG-Anteil</td><td id="dsv_agSv">{_esc(d.get("agSv") or "")}</td></tr>
        <tr><td>Zus. AG-Kosten</td><td id="dsv_agExtra">{_esc(d.get("agExtra") or "")}</td></tr>
        <tr><td>Gesamtkosten</td><td id="dsv_agTotal">{_esc(d.get("agTotal") or "")}</td></tr>
      </table>
      <div class="ds-pay">
        <span>Auszahlungsbetrag</span>
        <strong id="dsv_payout">{_esc(d.get("payout") or "")}</strong>
      </div>
    </div>
    <div class="ds-legal">
      <div>WorkPass Lohn · Form LOHN</div>
      <div class="ds-legal-center">– Entgeltbescheinigung nach § 108 Abs. 3 Satz 1 GewO –</div>
      <div class="ds-mark">Suppix AI</div>
    </div>
  </div>
</div>
""".strip()


def normalize_sheet_theme(theme: Any) -> str:
    raw = str(theme or "").strip().lower()
    if raw in {"black", "dark", "theme-black", "theme-dark"}:
        return "dark"
    return "light"


def fill_empty_sheet_fields(html_doc: str, data: dict[str, Any] | None) -> str:
    """Fill empty DatevSheet cells; also replace a truncated Steuer-ID with the full number."""
    import re

    data = data if isinstance(data, dict) else {}
    mapping = {
        "dsv_kkName": data.get("kkName"),
        "dsv_kkPct": data.get("kkPct"),
        "dsv_persNr": data.get("persNr"),
        "dsv_birth": data.get("birth"),
        "dsv_stkl": data.get("stkl"),
        "dsv_svNr": data.get("svNr"),
        "dsv_konf": data.get("konf"),
        "dsv_taxIdMid": data.get("taxIdMid"),
    }

    def _repl(match: re.Match[str]) -> str:
        attrs, inner = match.group(1), match.group(2)
        eid_m = re.search(r'\bid=["\'](dsv_[^"\']+)["\']', attrs, flags=re.I)
        if not eid_m:
            return match.group(0)
        value = _first_filled(mapping.get(eid_m.group(1)))
        if not value:
            return match.group(0)
        inner_s = str(inner or "").strip()
        if inner_s:
            # DATEV print often stores only the first 4 Steuer-ID digits — replace with the full number.
            if eid_m.group(1) != "dsv_taxIdMid":
                return match.group(0)
            if len(_digits_only(value)) <= len(_digits_only(inner_s)):
                return match.group(0)
        return f"<span{attrs}>{_esc(value)}</span>"

    return re.sub(
        r'<span([^>]*\bid=["\']dsv_[^"\']+["\'][^>]*)>(.*?)</span>',
        _repl,
        str(html_doc or ""),
        flags=re.I | re.S,
    )


def apply_sheet_chrome(html_doc: str, *, theme: Any = "light") -> str:
    """Center A4 sheet and tint page chrome to match admin theme (paper stays white)."""
    doc = str(html_doc or "")
    mode = normalize_sheet_theme(theme)
    chrome_class = f"sheet-chrome theme-{mode}"
    chrome_style = (
        "margin:0;min-height:100vh;box-sizing:border-box;"
        "display:flex;justify-content:center;align-items:flex-start;"
        f"padding:16px;overflow:auto;background:{'#0b1220' if mode == 'dark' else '#e8edf2'};"
    )
    # Prefer rewriting an existing body tag (Lohn live HTML or local).
    import re

    def _body_repl(match: re.Match[str]) -> str:
        attrs = match.group(1) or ""
        # Drop old style/class so chrome wins.
        attrs = re.sub(r'\sclass=(["\']).*?\1', "", attrs, flags=re.I)
        attrs = re.sub(r'\sstyle=(["\']).*?\1', "", attrs, flags=re.I)
        return f'<body class="{chrome_class}" style="{chrome_style}"{attrs}>'

    if re.search(r"<body\b", doc, flags=re.I):
        doc = re.sub(r"<body([^>]*)>", _body_repl, doc, count=1, flags=re.I)
    else:
        doc = f'<body class="{chrome_class}" style="{chrome_style}">{doc}</body>'
    # Ensure chrome CSS exists even for live Lohn HTML that lacks it.
    if "body.sheet-chrome" not in doc:
        inject = (
            "<style>"
            "body.sheet-chrome{margin:0;min-height:100vh;box-sizing:border-box;"
            "display:flex;justify-content:center;align-items:flex-start;padding:16px;overflow:auto}"
            "body.sheet-chrome.theme-light{background:#e8edf2}"
            "body.sheet-chrome.theme-dark{background:#0b1220}"
            ".datev-sheet-a4{margin:0 auto}"
            "</style>"
        )
        if re.search(r"</head>", doc, flags=re.I):
            doc = re.sub(r"</head>", inject + "</head>", doc, count=1, flags=re.I)
        else:
            doc = inject + doc
    return doc


def build_payslip_print_html(
    payslip: dict[str, Any] | None,
    *,
    job: dict[str, Any] | None = None,
    theme: Any = "light",
) -> str:
    data = payslip_to_sheet_data(payslip, job=job)
    body = build_sheet_body_html(data)
    period = str((payslip or {}).get("period") or (job or {}).get("period") or "")
    mode = normalize_sheet_theme(theme)
    html_doc = f"""<!DOCTYPE html>
<html lang="de"><head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Entgeltabrechnung {_esc(period)}</title>
<style>{_CSS}</style>
</head>
<body class="sheet-chrome theme-{mode}">
{body}
</body></html>"""
    return apply_sheet_chrome(html_doc, theme=mode)


def prepare_sheet_html_for_pdf(html_doc: str) -> str:
    """White A4 only — drop studio chrome padding so the worker PDF matches the sheet."""
    import re

    doc = str(html_doc or "").strip()
    if not doc:
        return ""
    print_css = """
@page { size: A4 portrait; margin: 0; }
html, body {
  margin: 0 !important; padding: 0 !important; background: #fff !important;
  min-height: auto !important; width: 210mm; height: 297mm;
  display: block !important; overflow: hidden !important;
}
body.sheet-chrome, body.sheet-chrome.theme-light, body.sheet-chrome.theme-dark {
  background: #fff !important; padding: 0 !important; min-height: auto !important;
  display: block !important; overflow: hidden !important; align-items: stretch !important;
}
.datev-sheet-a4 {
  margin: 0 !important; box-shadow: none !important;
  width: 210mm !important; height: 297mm !important;
}
.payslip-viewer-bar, .payslip-viewer-stage { display: none !important; }
.payslip-viewer-stage .datev-sheet-a4 { display: flex !important; }
"""
    if re.search(r"</head>", doc, flags=re.I):
        doc = re.sub(r"</head>", f"<style>{print_css}</style></head>", doc, count=1, flags=re.I)
    elif re.search(r"<body\b", doc, flags=re.I):
        doc = f"<!DOCTYPE html><html lang='de'><head><meta charset='UTF-8'/><style>{print_css}</style></head>{doc}</html>"
    else:
        doc = (
            "<!DOCTYPE html><html lang='de'><head><meta charset='UTF-8'/>"
            f"<style>{print_css}</style></head><body>{doc}</body></html>"
        )
    return doc


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
