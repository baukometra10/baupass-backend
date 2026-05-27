"""
Per-tenant data residency (multi-region isolation policy).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


def current_deployment_region() -> str:
    return (
        os.getenv("BAUPASS_REGION")
        or os.getenv("RAILWAY_REPLICA_REGION")
        or os.getenv("AWS_REGION")
        or ""
    ).strip() or "unknown"


def get_company_residency(db, company_id: int) -> dict[str, Any]:
    try:
        row = db.execute(
            """
            SELECT company_id, data_region, policy, updated_at
            FROM company_data_residency
            WHERE company_id = ?
            LIMIT 1
            """,
            (company_id,),
        ).fetchone()
        if row:
            return dict(row)
    except Exception:
        pass
    return {
        "company_id": company_id,
        "data_region": current_deployment_region(),
        "policy": "default",
        "updated_at": "",
    }


def set_company_residency(db, company_id: int, data_region: str, policy: str = "strict") -> dict[str, Any]:
    region = (data_region or "").strip() or current_deployment_region()
    pol = (policy or "strict").strip().lower()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    db.execute(
        """
        INSERT INTO company_data_residency (company_id, data_region, policy, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(company_id) DO UPDATE SET
            data_region = excluded.data_region,
            policy = excluded.policy,
            updated_at = excluded.updated_at
        """,
        (company_id, region, pol, now),
    )
    db.commit()
    return {"company_id": company_id, "data_region": region, "policy": pol, "updated_at": now}


def residency_allows_request(db, company_id: int | None) -> tuple[bool, str]:
    if not company_id:
        return True, ""
    enforce = os.getenv("BAUPASS_ENFORCE_DATA_RESIDENCY", "0").strip().lower() in {"1", "true", "yes"}
    if not enforce:
        return True, ""
    residency = get_company_residency(db, int(company_id))
    if residency.get("policy") != "strict":
        return True, ""
    required = str(residency.get("data_region") or "").strip()
    current = current_deployment_region()
    if required and current != "unknown" and required != current:
        return False, "data_residency_region_mismatch"
    return True, ""
