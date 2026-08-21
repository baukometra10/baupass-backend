"""Durable transfer job store (memory + disk mirror)."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def _jobs_dir() -> Path:
    try:
        from backend.server import BASE_DIR

        root = Path(BASE_DIR) / "backend" / "uploads" / "transfer_jobs"
    except Exception:
        root = Path("backend") / "uploads" / "transfer_jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _persist(job: dict[str, Any]) -> None:
    try:
        path = _jobs_dir() / f"{job['id']}.json"
        path.write_text(json.dumps(job, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception:
        pass


def _load(job_id: str) -> dict[str, Any] | None:
    try:
        path = _jobs_dir() / f"{job_id}.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def create_job(*, actor: str, mode: str, filename: str = "", company_id: str = "") -> str:
    job_id = f"xfer-{uuid.uuid4().hex[:16]}"
    job = {
        "id": job_id,
        "status": "queued",
        "mode": mode,
        "actor": actor,
        "filename": filename,
        "companyId": company_id or "",
        "percent": 0,
        "phase": "queued",
        "message": "",
        "domain": "",
        "createdAt": time.time(),
        "updatedAt": time.time(),
        "result": None,
        "error": None,
    }
    with _LOCK:
        _JOBS[job_id] = job
        _persist(job)
    return job_id


def update_job(job_id: str, **fields: Any) -> None:
    with _LOCK:
        job = _JOBS.get(job_id) or _load(job_id)
        if not job:
            return
        job.update(fields)
        job["updatedAt"] = time.time()
        _JOBS[job_id] = job
        _persist(job)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job:
            return dict(job)
    loaded = _load(job_id)
    if loaded:
        with _LOCK:
            _JOBS[job_id] = loaded
        return dict(loaded)
    return None


def list_recent_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with _LOCK:
        for path in _jobs_dir().glob("xfer-*.json"):
            jid = path.stem
            if jid not in _JOBS:
                loaded = _load(jid)
                if loaded:
                    _JOBS[jid] = loaded
        rows = sorted(_JOBS.values(), key=lambda j: j.get("createdAt") or 0, reverse=True)
        return [dict(r) for r in rows[: max(1, min(limit, 100))]]
