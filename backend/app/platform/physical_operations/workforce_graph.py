"""Workforce Graph Intelligence — co-access, teams, operational relationships."""
from __future__ import annotations

from typing import Any


def build_workforce_graph(db, company_id: int, *, days: int = 14) -> dict[str, Any]:
    days = max(3, min(days, 60))
    since = f"datetime('now', '-{days} days')"
    cid = str(company_id)
    pairs = db.execute(
        f"""
        SELECT al1.worker_id AS w1, al2.worker_id AS w2,
               COUNT(DISTINCT substr(al1.timestamp, 1, 10)) AS co_access_days,
               w1.site AS site
        FROM access_logs al1
        JOIN access_logs al2
          ON substr(al1.timestamp, 1, 10) = substr(al2.timestamp, 1, 10)
         AND al1.worker_id < al2.worker_id
         AND al2.direction = 'check-in'
        JOIN workers w1 ON w1.id = al1.worker_id
        JOIN workers w2 ON w2.id = al2.worker_id
        WHERE w1.company_id = ? AND w2.company_id = ?
          AND al1.direction = 'check-in'
          AND al1.timestamp >= {since}
        GROUP BY al1.worker_id, al2.worker_id
        HAVING co_access_days >= 2
        ORDER BY co_access_days DESC
        LIMIT 80
        """,
        (cid, cid),
    ).fetchall()
    edges = []
    for r in pairs:
        edges.append(
            {
                "source": r["w1"],
                "target": r["w2"],
                "weight": int(r["co_access_days"]),
                "relationship": "co_access",
                "site": r["site"],
            }
        )
    site_clusters = db.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(site), ''), 'Unassigned') AS site,
               COUNT(*) AS workers
        FROM workers
        WHERE company_id = ? AND deleted_at IS NULL
        GROUP BY site ORDER BY workers DESC
        """,
        (company_id,),
    ).fetchall()
    teams = []
    for s in site_clusters:
        if int(s["workers"] or 0) < 2:
            continue
        members = db.execute(
            "SELECT id, first_name, last_name FROM workers WHERE company_id = ? AND site = ? AND deleted_at IS NULL LIMIT 50",
            (company_id, s["site"] if s["site"] != "Unassigned" else ""),
        ).fetchall()
        teams.append(
            {
                "site": s["site"],
                "size": s["workers"],
                "members": [{"id": m["id"], "name": f"{m['first_name']} {m['last_name']}".strip()} for m in members],
            }
        )
    nodes = db.execute(
        "SELECT id, first_name, last_name, site FROM workers WHERE company_id = ? AND deleted_at IS NULL LIMIT 300",
        (company_id,),
    ).fetchall()
    return {
        "layer": "workforce_graph_intelligence",
        "periodDays": days,
        "nodes": [
            {"id": n["id"], "label": f"{n['first_name']} {n['last_name']}".strip(), "site": n["site"]}
            for n in nodes
        ],
        "edges": edges,
        "teamsBySite": teams[:20],
        "metrics": {"edgeCount": len(edges), "teamCount": len(teams)},
    }
