"""Companies document-email overview PDF."""
from __future__ import annotations

from backend.app.platform.reports.table_pdf import build_table_report_pdf


def build_companies_document_email_pdf(db) -> bytes:
    from backend.server import datetime, now_iso

    rows = db.execute(
        """
        SELECT
            c.name,
            c.document_email,
            c.status,
            c.billing_email,
            MAX(e.received_at) AS last_inbox_activity_at,
            SUM(CASE WHEN e.dismissed = 0 THEN 1 ELSE 0 END) AS open_inbox_count,
            SUM(CASE WHEN e.dismissed = 0 AND e.matched_company_id IS NULL
                AND lower(e.to_addr) = lower(c.document_email) THEN 1 ELSE 0 END) AS unresolved_inbox_count,
            c.deleted_at
        FROM companies c
        LEFT JOIN email_inbox e ON (e.matched_company_id = c.id OR lower(e.to_addr) = lower(c.document_email))
        GROUP BY c.id, c.name, c.document_email, c.status, c.billing_email, c.deleted_at
        ORDER BY c.name
        """
    ).fetchall()
    table_rows = []
    for row in rows:
        table_rows.append(
            (
                str(row["name"] or "")[:24],
                str(row["document_email"] or "")[:28],
                str(row["status"] or ""),
                str(row["billing_email"] or "")[:28],
                str(row["last_inbox_activity_at"] or "")[:18],
                int(row["open_inbox_count"] or 0),
                int(row["unresolved_inbox_count"] or 0),
                "ja" if row["deleted_at"] else "nein",
            )
        )
    subtitle = f"Erstellt: {datetime.now().strftime('%d.%m.%Y %H:%M')} / {now_iso()[:10]}"
    headers = ("Firma", "Dokument-E-Mail", "Status", "Rechnungs-E-Mail", "Letzter Eingang", "Offen", "Ungelöst", "Gelöscht")
    return build_table_report_pdf(
        title="BauPass — Firmen Dokument-E-Mails",
        subtitle=subtitle,
        headers=headers,
        rows=table_rows,
        landscape_mode=True,
    )
