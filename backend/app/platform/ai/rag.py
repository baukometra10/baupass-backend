"""Lightweight RAG — worker documents, compliance notes, recent audit hints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def search_knowledge(db, company_id: str, query: str, *, limit: int = 12) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if len(q) < 2:
        return []

    limit = min(20, max(1, limit))
    like = f"%{q}%"
    chunks: list[dict[str, Any]] = []

    try:
        docs = db.execute(
            """
            SELECT w.id AS worker_id, w.first_name, w.last_name, wd.doc_type, wd.expiry_date,
                   wd.filename, wd.notes
            FROM worker_documents wd
            JOIN workers w ON w.id = wd.worker_id
            WHERE w.company_id = ? AND w.deleted_at IS NULL
              AND (wd.doc_type LIKE ? OR wd.filename LIKE ? OR wd.notes LIKE ?
                   OR w.first_name LIKE ? OR w.last_name LIKE ?)
            ORDER BY wd.expiry_date ASC
            LIMIT ?
            """,
            (company_id, like, like, like, like, like, limit),
        ).fetchall()
        for d in docs:
            note = (d["notes"] or "")[:120]
            chunks.append(
                {
                    "source": "worker_documents",
                    "text": (
                        f"Worker {d['first_name']} {d['last_name']} ({d['worker_id']}): "
                        f"doc {d['doc_type']}, expires {d['expiry_date'] or 'n/a'}, "
                        f"file {d['filename'] or ''}{(' — ' + note) if note else ''}"
                    ),
                }
            )
    except Exception:
        pass

    try:
        audits = db.execute(
            """
            SELECT event_type, message, created_at
            FROM audit_logs
            WHERE company_id = ? AND (event_type LIKE ? OR message LIKE ?)
            ORDER BY created_at DESC LIMIT ?
            """,
            (company_id, like, like, min(6, limit)),
        ).fetchall()
        for a in audits:
            chunks.append(
                {
                    "source": "audit_logs",
                    "text": f"{a['created_at']}: {a['event_type']} — {(a['message'] or '')[:200]}",
                }
            )
    except Exception:
        pass

    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        mem = db.execute(
            """
            SELECT kind, key, value, importance, source, updated_at
            FROM ai_company_memory
            WHERE company_id = ?
              AND (expires_at IS NULL OR expires_at = '' OR expires_at > ?)
              AND (value LIKE ? OR key LIKE ? OR kind LIKE ?)
            ORDER BY importance DESC, updated_at DESC
            LIMIT ?
            """,
            (company_id, now, like, like, like, min(8, limit)),
        ).fetchall()
        for m in mem:
            chunks.append(
                {
                    "source": "company_memory",
                    "title": f"memory:{m['kind']}:{m['key'] or ''}",
                    "text": f"[{m['kind']}] {m['key'] or ''}: {(m['value'] or '')[:300]}",
                }
            )
    except Exception:
        pass

    return chunks[:limit]
