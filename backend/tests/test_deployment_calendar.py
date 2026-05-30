"""Deployment calendar month bounds."""
from backend.app.platform.workforce.deployment_store import month_bounds


def test_month_bounds():
    start, end = month_bounds(2026, 5)
    assert start == "2026-05-01"
    assert end == "2026-05-31"
