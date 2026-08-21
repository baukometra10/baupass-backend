"""Partner-ready scaffolds for DATEV LODAS and ELSTER (not officially certified)."""
from __future__ import annotations

import json
import time
from typing import Any


PARTNER_STATES = ("sandbox", "pending_cert", "live")


def ensure_partner_schema(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS partner_cert_pipelines (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            program TEXT NOT NULL,
            state TEXT NOT NULL,
            package_json TEXT NOT NULL DEFAULT '{}',
            validation_json TEXT NOT NULL DEFAULT '{}',
            audit_json TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL
        )
        """
    )
    db.commit()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_datev_lodas_package(db, company_id: str, *, period: str = "") -> dict[str, Any]:
    """Build a LODAS-oriented payroll package for partner certification sandboxes."""
    from .payroll_adapter import build_datev_payroll_csv, payroll_export_preview

    preview = payroll_export_preview(db, company_id, period=period)
    csv_text = build_datev_payroll_csv(db, company_id, period=period)
    rows = list(preview.get("rows") or [])
    validation = {
        "rowCount": len(rows),
        "hasPeriod": bool(period),
        "csvBytes": len(csv_text.encode("utf-8")),
        "schema": "datev_lodas_partner_v1",
        "errors": [] if rows else ["no_payroll_rows"],
        "ok": bool(rows),
    }
    return {
        "ok": True,
        "program": "datev_lodas",
        "state": "sandbox",
        "certified": False,
        "period": period or preview.get("period"),
        "package": {
            "format": "datev_lodas_partner_v1",
            "csv": csv_text,
            "rows": rows[:500],
        },
        "validation": validation,
        "checklist": [
            "Join DATEV partner program",
            "Upload package to DATEV sandbox",
            "Pass format validation",
            "Receive LODAS certification",
        ],
    }


def build_elster_package(db, company_id: str, *, tax_year: str = "") -> dict[str, Any]:
    """Scaffold ELSTER transmission package (certificate enrollment still external)."""
    year = str(tax_year or time.strftime("%Y")).strip()
    workers = 0
    try:
        row = db.execute(
            "SELECT COUNT(*) AS c FROM workers WHERE company_id = ? AND deleted_at IS NULL",
            (str(company_id),),
        ).fetchone()
        workers = int(row["c"] if hasattr(row, "keys") else row[0])
    except Exception:
        workers = 0
    validation = {
        "taxYear": year,
        "workerCount": workers,
        "certificateConfigured": False,
        "errors": ["elster_certificate_enrollment_required"],
        "ok": False,
    }
    return {
        "ok": True,
        "program": "elster",
        "state": "sandbox",
        "certified": False,
        "package": {
            "format": "elster_partner_v1",
            "taxYear": year,
            "companyId": str(company_id),
            "workerCount": workers,
        },
        "validation": validation,
        "checklist": [
            "Obtain ELSTER organization certificate",
            "Map wage tax / social forms",
            "Validate against ELSTER test portal",
            "Enable live transmission after authority approval",
        ],
    }


def save_partner_pipeline(db, *, company_id: str, program: str, state: str, package: dict, validation: dict) -> dict[str, Any]:
    ensure_partner_schema(db)
    if state not in PARTNER_STATES:
        return {"ok": False, "error": "invalid_state"}
    pid = f"pc-{program}-{company_id}"
    now = _now()
    audit = [{"at": now, "state": state}]
    db.execute(
        """
        INSERT INTO partner_cert_pipelines (id, company_id, program, state, package_json, validation_json, audit_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            state = excluded.state,
            package_json = excluded.package_json,
            validation_json = excluded.validation_json,
            audit_json = excluded.audit_json,
            updated_at = excluded.updated_at
        """,
        (
            pid,
            str(company_id),
            str(program),
            state,
            json.dumps(package, ensure_ascii=False)[:200000],
            json.dumps(validation, ensure_ascii=False)[:20000],
            json.dumps(audit, ensure_ascii=False),
            now,
        ),
    )
    db.commit()
    return {"ok": True, "id": pid, "program": program, "state": state, "certified": False}


def partner_readiness_summary(db, company_id: str) -> dict[str, Any]:
    ensure_partner_schema(db)
    rows = db.execute(
        "SELECT program, state, updated_at FROM partner_cert_pipelines WHERE company_id = ?",
        (str(company_id),),
    ).fetchall()
    by_program = {str(r["program"]): {"state": r["state"], "updatedAt": r["updated_at"]} for r in rows}
    tech_score = 0
    if "datev_lodas" in by_program:
        tech_score += 50
    if "elster" in by_program:
        tech_score += 40
    if by_program.get("datev_lodas", {}).get("state") == "pending_cert":
        tech_score += 5
    if by_program.get("elster", {}).get("state") == "pending_cert":
        tech_score += 5
    return {
        "ok": True,
        "companyId": str(company_id),
        "technicalPercent": min(100, tech_score),
        "officiallyCertified": False,
        "programs": by_program,
        "doNotPromise": ["DATEV LODAS certified", "ELSTER certified transmission"],
    }
