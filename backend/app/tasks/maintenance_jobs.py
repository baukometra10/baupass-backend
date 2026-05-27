"""
Scheduled maintenance jobs (RQ / on-demand).
"""
from __future__ import annotations


def run_access_log_archive() -> dict:
    from backend.server import get_db
    from backend.app.tasks.access_logs_archive import archive_access_logs

    return archive_access_logs(get_db())
