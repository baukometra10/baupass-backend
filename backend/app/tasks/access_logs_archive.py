"""
Archive old access_logs rows into access_logs_archive (retention policy).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


def archive_access_logs(db, *, retention_days: int | None = None, batch_size: int = 5000) -> dict[str, Any]:
    days = retention_days or int(os.getenv("BAUPASS_ACCESS_LOG_RETENTION_DAYS", "365"))
    days = max(30, days)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    moved = 0
    while True:
        rows = db.execute(
            """
            SELECT al.id, w.company_id, al.worker_id, al.direction, al.gate, al.timestamp
            FROM access_logs al
            LEFT JOIN workers w ON w.id = al.worker_id
            WHERE al.timestamp < ?
            ORDER BY al.timestamp ASC
            LIMIT ?
            """,
            (cutoff, batch_size),
        ).fetchall()
        if not rows:
            break
        for row in rows:
            archive_id = f"arch-{uuid.uuid4().hex[:12]}"
            db.execute(
                """
                INSERT OR IGNORE INTO access_logs_archive
                    (id, company_id, worker_id, direction, gate, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    archive_id,
                    str(row["company_id"] if row["company_id"] is not None else ""),
                    row["worker_id"],
                    row["direction"],
                    row.get("gate") if hasattr(row, "get") else row["gate"],
                    row["timestamp"],
                ),
            )
            db.execute("DELETE FROM access_logs WHERE id = ?", (row["id"],))
            moved += 1
        db.commit()
        if len(rows) < batch_size:
            break
    return {"ok": True, "archived": moved, "retentionDays": days, "cutoff": cutoff}
