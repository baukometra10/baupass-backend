from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def run_contract_sign_reminders(db, *, base_url: str = "", min_age_days: int = 3) -> dict[str, Any]:
    """Send reminder e-mails for pending sign sessions older than min_age_days."""
    from .service import ContractsService

    service = ContractsService(db)
    pending = service.repo.list_pending_sign_sessions_for_reminder(min_age_days=min_age_days)
    sent = 0
    skipped = 0
    errors = 0
    for row in pending:
        try:
            ok = service.send_sign_session_reminder(row, base_url=base_url)
            if ok:
                sent += 1
            else:
                skipped += 1
        except Exception as exc:
            errors += 1
            logger.warning("contract sign reminder failed for %s: %s", row.get("id"), exc)
    return {"sent": sent, "skipped": skipped, "errors": errors, "checked": len(pending)}


def contract_reminder_loop(flask_app, get_db, base_url: str = "", interval_seconds: int = 3600) -> None:
    import time

    while True:
        try:
            with flask_app.app_context():
                db = get_db()
                result = run_contract_sign_reminders(db, base_url=base_url)
                if result.get("sent"):
                    logger.info("Contract sign reminders sent: %s", result)
        except Exception as exc:
            logger.warning("Contract reminder loop error: %s", exc)
        time.sleep(max(300, interval_seconds))
