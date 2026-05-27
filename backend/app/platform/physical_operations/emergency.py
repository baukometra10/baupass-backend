"""Smart Emergency — evacuation, roll call, inside/out/missing."""
from __future__ import annotations

from typing import Any

from ._common import list_on_site_workers, now_iso, today_prefix


def get_emergency(db, emergency_id: str, company_id: int) -> dict | None:
    row = db.execute(
        "SELECT * FROM emergency_events WHERE id = ? AND company_id = ?",
        (emergency_id, company_id),
    ).fetchone()
    return dict(row) if row else None


def start_roll_call(db, emergency_id: str, company_id: int, *, marked_by: str = "") -> dict[str, Any]:
    em = get_emergency(db, emergency_id, company_id)
    if not em:
        return {"error": "emergency_not_found"}
    on_site = list_on_site_workers(db, company_id)
    all_workers = db.execute(
        "SELECT id FROM workers WHERE company_id = ? AND deleted_at IS NULL",
        (company_id,),
    ).fetchall()
    on_site_ids = {w["id"] for w in on_site}
    created = 0
    for w in all_workers:
        wid = w["id"]
        expected = 1 if wid in on_site_ids else 0
        status = "on_site" if expected else "off_site"
        rid = f"rc-{emergency_id}-{wid}"[:120]
        try:
            db.execute(
                """
                INSERT OR REPLACE INTO emergency_roll_calls
                    (id, emergency_id, company_id, worker_id, expected_on_site, status,
                     last_gate, last_seen_at, marked_at, marked_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    rid,
                    emergency_id,
                    company_id,
                    wid,
                    expected,
                    status,
                    next((x.get("gate") for x in on_site if x["id"] == wid), ""),
                    next((x.get("last_access") for x in on_site if x["id"] == wid), None),
                    marked_by,
                    now_iso(),
                ),
            )
            created += 1
        except Exception:
            pass
    db.commit()
    return build_emergency_status(db, emergency_id, company_id)


def mark_roll_call(
    db,
    emergency_id: str,
    company_id: int,
    worker_id: str,
    status: str,
    *,
    marked_by: str = "",
) -> dict[str, Any]:
    allowed = {"safe", "evacuated", "missing", "on_site", "off_site"}
    if status not in allowed:
        return {"error": "invalid_status", "allowed": sorted(allowed)}
    db.execute(
        """
        UPDATE emergency_roll_calls
        SET status = ?, marked_at = ?, marked_by = ?
        WHERE emergency_id = ? AND company_id = ? AND worker_id = ?
        """,
        (status, now_iso(), marked_by, emergency_id, company_id, worker_id),
    )
    db.commit()
    return build_emergency_status(db, emergency_id, company_id)


def build_emergency_status(db, emergency_id: str, company_id: int) -> dict[str, Any]:
    em = get_emergency(db, emergency_id, company_id)
    if not em:
        return {"error": "emergency_not_found"}
    today = today_prefix()
    on_site_now = list_on_site_workers(db, company_id, today)
    on_site_ids = {w["id"] for w in on_site_now}
    rows = []
    try:
        rows = db.execute(
            "SELECT * FROM emergency_roll_calls WHERE emergency_id = ? AND company_id = ?",
            (emergency_id, company_id),
        ).fetchall()
    except Exception:
        pass
    roll = [dict(r) for r in rows]
    if not roll:
        start_roll_call(db, emergency_id, company_id)
        rows = db.execute(
            "SELECT * FROM emergency_roll_calls WHERE emergency_id = ? AND company_id = ?",
            (emergency_id, company_id),
        ).fetchall()
        roll = [dict(r) for r in rows]
    missing = [r for r in roll if r.get("expected_on_site") and r.get("status") not in ("safe", "evacuated", "off_site")]
    inside = [r for r in roll if r.get("status") in ("on_site", "missing") or r["worker_id"] in on_site_ids]
    evacuated = [r for r in roll if r.get("status") == "evacuated"]
    workers_detail = db.execute(
        """
        SELECT w.id, w.first_name, w.last_name, w.site, w.contact
        FROM workers w WHERE w.company_id = ? AND w.deleted_at IS NULL
        """,
        (company_id,),
    ).fetchall()
    name_map = {r["id"]: f"{r['first_name']} {r['last_name']}".strip() for r in workers_detail}
    return {
        "layer": "smart_emergency",
        "emergency": em,
        "summary": {
            "expectedOnSite": sum(1 for r in roll if r.get("expected_on_site")),
            "markedSafe": sum(1 for r in roll if r.get("status") in ("safe", "evacuated")),
            "missing": len(missing),
            "currentlyInside": len(on_site_ids),
            "evacuated": len(evacuated),
        },
        "insideNow": [
            {"workerId": w["id"], "name": f"{w.get('first_name','')} {w.get('last_name','')}".strip(), "gate": w.get("gate")}
            for w in on_site_now
        ],
        "missingPersons": [
            {"workerId": r["worker_id"], "name": name_map.get(r["worker_id"], r["worker_id"]), "status": r["status"]}
            for r in missing
        ],
        "rollCall": roll,
    }
