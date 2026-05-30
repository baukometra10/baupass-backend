"""
Payroll integration adapter (structured export; DATEV-friendly CSV).
"""
from __future__ import annotations

import csv
import io
from typing import Any

from backend.app.platform.worker_documents import WORKER_PAYROLL_DOC_TYPES, doc_type_label


def payroll_export_preview(db, company_id: str, *, period: str = "") -> dict[str, Any]:
    rows = db.execute(
        """
        SELECT w.id, w.first_name, w.last_name, w.badge_id, w.insurance_number, w.status,
               COUNT(al.id) AS access_events
        FROM workers w
        LEFT JOIN access_logs al ON al.worker_id = w.id
            AND (? = '' OR substr(al.timestamp, 1, 7) = ?)
        WHERE w.company_id = ? AND w.deleted_at IS NULL
        GROUP BY w.id
        ORDER BY w.last_name, w.first_name
        LIMIT 500
        """,
        (period, period, company_id),
    ).fetchall()
    payroll_docs = list_payroll_documents(db, company_id, period=period)
    return {
        "ok": True,
        "provider": "payroll",
        "period": period or "all",
        "rows": [dict(r) for r in rows],
        "payrollDocuments": payroll_docs,
        "format": "baupass_payroll_v1",
        "datevCsvAvailable": True,
        "note": "DATEV-CSV unter /api/documents/payroll/datev-export oder Enterprise-Integration",
    }


def list_payroll_documents(db, company_id: str, *, period: str = "") -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in WORKER_PAYROLL_DOC_TYPES)
    params: list[Any] = [company_id, *sorted(WORKER_PAYROLL_DOC_TYPES)]
    period_clause = ""
    if period:
        period_clause = " AND substr(created_at, 1, 7) = ?"
        params.append(period)
    rows = db.execute(
        f"""
        SELECT wd.id, wd.worker_id, wd.doc_type, wd.filename, wd.created_at,
               w.first_name, w.last_name, w.badge_id
        FROM worker_documents wd
        JOIN workers w ON w.id = wd.worker_id
        WHERE wd.company_id = ?
          AND wd.doc_type IN ({placeholders})
          {period_clause}
        ORDER BY wd.created_at DESC
        LIMIT 200
        """,
        tuple(params),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "workerId": r["worker_id"],
            "docType": r["doc_type"],
            "docTypeLabel": doc_type_label(r["doc_type"], "de"),
            "filename": r["filename"],
            "createdAt": r["created_at"],
            "workerName": f"{r['first_name']} {r['last_name']}".strip(),
            "badgeId": r["badge_id"],
        }
        for r in rows
    ]


def build_datev_payroll_csv(db, company_id: str, *, period: str = "") -> str:
    """
    Simplified DATEV-oriented CSV (Stunden + Stammdaten-Hinweise) for payroll handoff.
    Columns: Personalnummer;Nachname;Vorname;Badge;Zeitraum;CheckIns;LetzteAbrechnung;AbrechnungsTyp
    """
    period_val = (period or "").strip()[:7]
    company = db.execute("SELECT name FROM companies WHERE id = ?", (company_id,)).fetchone()
    company_name = str(company["name"] if company else "")

    rows = db.execute(
        """
        SELECT w.id, w.first_name, w.last_name, w.badge_id, w.insurance_number,
               COUNT(CASE WHEN al.direction = 'check-in' THEN 1 END) AS check_ins
        FROM workers w
        LEFT JOIN access_logs al ON al.worker_id = w.id
            AND (? = '' OR substr(al.timestamp, 1, 7) = ?)
        WHERE w.company_id = ? AND w.deleted_at IS NULL
        GROUP BY w.id
        ORDER BY w.last_name, w.first_name
        """,
        (period_val, period_val, company_id),
    ).fetchall()

    payroll_by_worker: dict[str, dict[str, str]] = {}
    for doc in list_payroll_documents(db, company_id, period=period_val):
        wid = str(doc.get("workerId") or "")
        if wid and wid not in payroll_by_worker:
            payroll_by_worker[wid] = doc

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "Mandant",
            "Personalnummer",
            "Nachname",
            "Vorname",
            "Badge",
            "Zeitraum",
            "CheckIns",
            "LetzteAbrechnung",
            "AbrechnungsTyp",
        ]
    )
    for row in rows:
        wid = str(row["id"])
        personal_no = str(row["insurance_number"] or row["badge_id"] or wid).strip()
        last_payroll = payroll_by_worker.get(wid, {})
        writer.writerow(
            [
                company_name,
                personal_no,
                str(row["last_name"] or "").strip(),
                str(row["first_name"] or "").strip(),
                str(row["badge_id"] or "").strip(),
                period_val or "gesamt",
                int(row["check_ins"] or 0),
                str(last_payroll.get("createdAt") or ""),
                str(last_payroll.get("docTypeLabel") or ""),
            ]
        )
    return buffer.getvalue()
