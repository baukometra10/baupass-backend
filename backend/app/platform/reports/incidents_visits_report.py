"""Incidents + active visitors PDF for email reporting."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _company_id_filter(user: dict[str, Any]) -> str | None:
    cid = str(user.get("company_id") or "").strip()
    if str(user.get("role") or "") == "superadmin" and not cid:
        return None
    return cid or None


def fetch_incidents_rows(db, company_id: str | None, *, limit: int = 200) -> list[list[str]]:
    if company_id:
        rows = db.execute(
            """
            SELECT incident_type, severity, status, description, created_at, resolved_at
            FROM incidents WHERE company_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT incident_type, severity, status, description, created_at, resolved_at
            FROM incidents ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        [
            str(r["incident_type"] or ""),
            str(r["severity"] or ""),
            str(r["status"] or ""),
            (str(r["description"] or ""))[:72],
            str(r["created_at"] or "")[:19],
            str(r["resolved_at"] or "")[:19] if r["resolved_at"] else "—",
        ]
        for r in rows
    ]


def fetch_visitor_rows(db, company_id: str | None, *, limit: int = 150) -> list[list[str]]:
    sql_base = """
        SELECT first_name, last_name, visitor_company, visit_purpose, host_name, valid_until, site
        FROM workers
        WHERE deleted_at IS NULL
          AND lower(COALESCE(worker_type, '')) = 'visitor'
          AND lower(COALESCE(status, '')) = 'aktiv'
    """
    if company_id:
        rows = db.execute(sql_base + " AND company_id = ? ORDER BY valid_until ASC LIMIT ?", (company_id, limit)).fetchall()
    else:
        rows = db.execute(sql_base + " ORDER BY valid_until ASC LIMIT ?", (limit,)).fetchall()
    return [
        [
            f"{r['first_name'] or ''} {r['last_name'] or ''}".strip(),
            str(r["visitor_company"] or ""),
            (str(r["visit_purpose"] or ""))[:36],
            str(r["host_name"] or ""),
            str(r["valid_until"] or "")[:19],
            str(r["site"] or ""),
        ]
        for r in rows
    ]


def build_incidents_visits_pdf(
    db,
    user: dict[str, Any],
    company_name: str,
    *,
    branding: dict[str, Any] | None = None,
) -> bytes:
    from backend.app.platform.reports.report_pdf_layout import build_branded_multi_table_report_pdf

    company_id = _company_id_filter(user)
    period = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    brand = dict(branding or {})
    if company_name:
        brand["companyName"] = company_name

    return build_branded_multi_table_report_pdf(
        report_title="Havarien & Besucher",
        subtitle=f"{company_name} · {period}",
        branding=brand,
        landscape_mode=True,
        tables=[
            {
                "title": "Incidents / Sicherheitsvorfälle",
                "headers": ["Typ", "Schwere", "Status", "Beschreibung", "Erstellt", "Gelöst"],
                "rows": fetch_incidents_rows(db, company_id),
            },
            {
                "title": "Besucher vor Ort",
                "headers": ["Name", "Firma", "Zweck", "Gastgeber", "Gültig bis", "Standort"],
                "rows": fetch_visitor_rows(db, company_id),
            },
        ],
    )
