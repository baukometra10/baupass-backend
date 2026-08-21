"""Legal-hold helpers shared by retention and GDPR erase paths."""
from __future__ import annotations

from typing import Any


def company_has_active_legal_hold(
    db,
    company_id: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    fail_closed: bool = True,
) -> bool:
    cid = str(company_id or "").strip()
    if not cid:
        return bool(fail_closed)
    try:
        rows = db.execute(
            """
            SELECT target_type, target_id FROM legal_holds
            WHERE company_id = ? AND active = 1
            """,
            (cid,),
        ).fetchall()
    except Exception:
        # Fail closed for destructive paths (erase/retention) when hold table is unavailable.
        return bool(fail_closed)
    if not rows:
        return False
    if target_type is None and target_id is None:
        return True
    for row in rows:
        tt = str(row["target_type"] if "target_type" in row.keys() else "")
        tid = str(row["target_id"] if "target_id" in row.keys() else "")
        if tt in {"company", "all"} and tid in {cid, "*", ""}:
            return True
        if target_type and tt == target_type and (not target_id or tid in {target_id, "*", ""}):
            return True
    return False


def assert_not_on_legal_hold(db, company_id: str, *, action: str = "mutate") -> dict[str, Any] | None:
    if company_has_active_legal_hold(db, company_id):
        return {
            "ok": False,
            "error": "legal_hold_active",
            "message": f"Blocked by active legal hold ({action}).",
        }
    return None
