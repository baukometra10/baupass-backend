"""SIEM CEF formatting."""
from __future__ import annotations

import unittest


def _cef_escape(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace("|", "\\|")


def audit_row_to_cef(row: dict) -> str:
    severity = 7 if str(row.get("event_type") or "").endswith(".failed") else 3
    ext = " ".join(
        [
            f"rt={_cef_escape(row.get('created_at') or '')}",
            f"msg={_cef_escape(row.get('message') or '')}",
        ]
    )
    return f"CEF:0|SUPPIX|ControlPass|1.0|{_cef_escape(row.get('event_type') or 'audit')}|Audit|{severity}|{ext}"


class SiemCefTests(unittest.TestCase):
    def test_cef_line_contains_event_type(self):
        line = audit_row_to_cef(
            {"event_type": "login.success", "created_at": "2026-05-30T12:00:00Z", "message": "ok"}
        )
        self.assertTrue(line.startswith("CEF:"))
        self.assertIn("login.success", line)


if __name__ == "__main__":
    unittest.main()
