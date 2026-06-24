"""Invoice summary PDF for email reporting."""
from __future__ import annotations

from typing import Any

from backend.app.platform.reports.table_pdf import build_table_report_pdf


def fetch_invoice_report_rows(db, *, company_id: str | None = None, include_paid: bool = False) -> list[tuple]:
    params: list[Any] = []
    clauses = ["1=1"]
    if company_id:
        clauses.append("invoices.company_id = ?")
        params.append(company_id)
    if not include_paid:
        clauses.append("invoices.paid_at IS NULL")
    where = " AND ".join(clauses)
    rows = db.execute(
        f"""
        SELECT companies.name AS company_name,
               invoices.invoice_number,
               invoices.invoice_date,
               invoices.due_date,
               invoices.total_amount,
               invoices.status,
               invoices.paid_at
        FROM invoices
        JOIN companies ON companies.id = invoices.company_id
        WHERE {where}
        ORDER BY companies.name, invoices.due_date, invoices.invoice_number
        LIMIT 500
        """,
        tuple(params),
    ).fetchall()
    result = []
    for row in rows:
        result.append(
            (
                str(row["company_name"] or "")[:24],
                str(row["invoice_number"] or ""),
                str(row["invoice_date"] or "")[:10],
                str(row["due_date"] or "")[:10],
                f"{float(row['total_amount'] or 0):.2f}",
                str(row["status"] or ""),
                "ja" if row["paid_at"] else "nein",
            )
        )
    return result


def build_invoices_report_pdf(db, *, company_id: str | None = None, company_name: str = "") -> bytes:
    from backend.server import now_iso

    rows = fetch_invoice_report_rows(db, company_id=company_id)
    title = "SUPPIX Rechnungsübersicht"
    if company_name:
        title = f"{title} — {company_name}"
    subtitle = f"Erstellt: {now_iso()[:19]} UTC · {len(rows)} Position(en)"
    headers = ("Firma", "Rechnung", "Datum", "Fällig", "Betrag EUR", "Status", "Bezahlt")
    return build_table_report_pdf(title=title, subtitle=subtitle, headers=headers, rows=rows, landscape_mode=True)
