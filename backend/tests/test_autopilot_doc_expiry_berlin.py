"""Compliance autopilot uses Berlin calendar helpers for document expiry."""
from unittest.mock import MagicMock, patch

from backend.app.platform.autopilot import runner


def test_auto_notify_document_expiry_uses_berlin_helpers():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []

    with (
        patch(
            "backend.app.platform.physical_operations._common.today_prefix",
            return_value="2026-07-21",
        ),
        patch(
            "backend.app.platform.physical_operations._common.calendar_day_offset",
            return_value="2026-08-04",
        ) as horizon_fn,
        patch.object(runner, "_recent_autopilot_audit", return_value=False),
    ):
        sent = runner._auto_notify_document_expiry(db, "co-1", 14)

    assert sent == 0
    horizon_fn.assert_called_once_with(14)
    sql_args = db.execute.call_args[0][1]
    assert sql_args == ("co-1", "2026-08-04", "2026-07-21")


def test_auto_notify_document_expiry_notifies_inbox_when_sent():
    db = MagicMock()
    row = {
        "id": "doc-1",
        "worker_id": "w-1",
        "doc_type": "Pass",
        "expiry_date": "2026-07-25",
        "first_name": "A",
        "last_name": "B",
    }
    db.execute.return_value.fetchall.return_value = [row]

    with (
        patch(
            "backend.app.platform.physical_operations._common.today_prefix",
            return_value="2026-07-21",
        ),
        patch(
            "backend.app.platform.physical_operations._common.calendar_day_offset",
            return_value="2026-08-04",
        ),
        patch.object(runner, "_recent_autopilot_audit", return_value=False),
        patch.object(runner, "_log_autopilot"),
        patch(
            "backend.app.platform.ai.actions.execute_action",
            return_value={"ok": True, "pushSent": 1},
        ),
        patch(
            "backend.app.platform.inbox.events.notify_inbox_changed"
        ) as notify,
    ):
        sent = runner._auto_notify_document_expiry(db, "co-1", 14)

    assert sent == 1
    notify.assert_called_once_with("co-1", source="document_expiry")
