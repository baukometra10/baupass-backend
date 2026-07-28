"""Worker morning-brief endpoint."""
from __future__ import annotations


def test_build_worker_morning_brief_empty_safe():
    from backend.app.domains.workers.morning_brief import build_worker_morning_brief

    class _Dummy:
        def execute(self, *_a, **_k):
            raise RuntimeError("no db")

    out = build_worker_morning_brief(_Dummy(), worker_id="w1", company_id="c1")
    assert out.get("ok") is True
    assert out.get("checkedInToday") is False
    assert isinstance(out.get("lines"), list)
