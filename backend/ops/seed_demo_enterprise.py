"""
Set demo / all active companies to enterprise plan (for customer demos).
Usage: BAUPASS_SEED_DEMO_ENTERPRISE=1 on boot, or:
  python -m backend.ops.seed_demo_enterprise
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def seed_demo_enterprise(db=None) -> dict:
    from backend.server import get_db

    conn = db or get_db()
    demo_ids = ["cmp-demo", "1"]
    updated = 0
    for cid in demo_ids:
        cur = conn.execute(
            "UPDATE companies SET plan = 'enterprise' WHERE id = ? AND deleted_at IS NULL",
            (str(cid),),
        )
        updated += cur.rowcount or 0
    cur2 = conn.execute(
        "UPDATE companies SET plan = 'enterprise' WHERE name LIKE '%Demo%' AND deleted_at IS NULL"
    )
    updated += cur2.rowcount or 0
    conn.commit()
    return {"updated": updated, "plan": "enterprise"}


if __name__ == "__main__":
    from backend.server import init_db

    init_db()
    print(seed_demo_enterprise())
