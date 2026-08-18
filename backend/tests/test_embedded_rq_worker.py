"""Embedded RQ worker stays off in tests and honors the disable flag."""
from __future__ import annotations

from backend.app.tasks.worker import rq_modes_enabled, start_embedded_worker


def test_rq_modes_include_dunning(monkeypatch):
    monkeypatch.setenv("BAUPASS_INVOICE_RETRY_MODE", "thread")
    monkeypatch.setenv("BAUPASS_WORKER_SESSION_CLEANUP_MODE", "thread")
    monkeypatch.setenv("BAUPASS_DAILY_JOBS_MODE", "thread")
    monkeypatch.setenv("BAUPASS_DUNNING_MODE", "rq")
    assert rq_modes_enabled() is True


def test_embedded_worker_skipped_in_testing(monkeypatch):
    monkeypatch.setenv("BAUPASS_ENV", "testing")
    monkeypatch.setenv("BAUPASS_DAILY_JOBS_MODE", "rq")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    assert start_embedded_worker() is False


def test_embedded_worker_skipped_when_disabled(monkeypatch):
    monkeypatch.setenv("BAUPASS_ENV", "production")
    monkeypatch.setenv("BAUPASS_EMBED_RQ_WORKER", "0")
    monkeypatch.setenv("BAUPASS_DAILY_JOBS_MODE", "rq")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    assert start_embedded_worker() is False
