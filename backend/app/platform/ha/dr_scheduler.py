"""Periodic Postgres DR snapshot trigger (safe no-op when not on Postgres)."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("baupass.ha.dr")


def maybe_run_scheduled_dr_snapshot() -> dict[str, Any]:
    """
    Invoked from RQ scheduler / boot hooks.

    Enable with BAUPASS_PG_DR_SNAPSHOT_SCHEDULE=1 (and Postgres runtime).
    Actual dump uses backend.ops.postgres_dr_snapshot when available.
    """
    enabled = (os.getenv("BAUPASS_PG_DR_SNAPSHOT_SCHEDULE") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        return {"ok": True, "skipped": True, "reason": "disabled"}

    try:
        from backend.app.db.runtime import postgres_runtime_enabled

        if not postgres_runtime_enabled():
            return {"ok": True, "skipped": True, "reason": "not_postgres"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    try:
        from backend.ops.postgres_dr_snapshot import run_dr_snapshot

        result = run_dr_snapshot(do_dump=True)
        logger.info("Scheduled DR snapshot finished: %s", result.get("status") or result.get("ok"))
        return {"ok": True, "result": result}
    except ImportError:
        # Fallback: call module main helpers if function name differs
        try:
            from backend.ops import postgres_dr_snapshot as mod

            if hasattr(mod, "collect_snapshot"):
                return {"ok": True, "result": mod.collect_snapshot()}
            return {"ok": True, "skipped": True, "reason": "no_run_helper"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.warning("DR snapshot failed: %s", exc)
        return {"ok": False, "error": str(exc)}
