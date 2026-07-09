"""Unit tests for background job health snapshots and deduplicated scheduling."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


def test_record_job_run_increments_consecutive_failures():
    from backend.app.tasks import job_health

    store: dict[str, str] = {}
    conn = MagicMock()

    def _setex(key, _ttl, value):
        store[key] = value

    def _get(key):
        return store.get(key)

    conn.setex.side_effect = _setex
    conn.get.side_effect = _get

    with patch.object(job_health, "_redis_conn", return_value=conn):
        job_health.record_job_run("daily_jobs", ok=False, error="boom")
        job_health.record_job_run("daily_jobs", ok=False, error="boom again")

    payload = json.loads(store["baupass:job:status:daily_jobs"])
    assert payload["consecutiveFailures"] == 2
    assert payload["ok"] is False
    assert "boom again" in payload["error"]


def test_record_job_run_resets_failures_on_success():
    from backend.app.tasks import job_health

    store: dict[str, str] = {}
    conn = MagicMock()
    conn.setex.side_effect = lambda key, _ttl, value: store.update({key: value})
    conn.get.side_effect = lambda key: store.get(key)

    with patch.object(job_health, "_redis_conn", return_value=conn):
        job_health.record_job_run("imap_poller", ok=False, error="x")
        job_health.record_job_run("imap_poller", ok=True, details={"processed": 1})

    payload = json.loads(store["baupass:job:status:imap_poller"])
    assert payload["consecutiveFailures"] == 0
    assert payload["ok"] is True


def test_scheduled_job_pending_true_for_queued_status():
    from backend.app.tasks import __init__ as tasks_mod

    job = MagicMock()
    job.get_status.return_value = "queued"
    mock_job_cls = MagicMock()
    mock_job_cls.fetch.return_value = job

    with patch.object(tasks_mod, "_redis_conn", MagicMock()):
        with patch("rq.job.Job", mock_job_cls):
            assert tasks_mod.scheduled_job_pending("baupass:scheduled:legacy.daily_jobs") is True


def test_enqueue_in_deduped_skips_when_pending():
    from backend.app.tasks import __init__ as tasks_mod

    with patch.object(tasks_mod, "scheduled_job_pending", return_value=True):
        with patch.object(tasks_mod, "enqueue_in") as enqueue_in:
            result = tasks_mod.enqueue_in_deduped(
                60,
                "scheduled",
                lambda: None,
                job_id="baupass:scheduled:legacy.dunning",
            )
    assert result is None
    enqueue_in.assert_not_called()


def test_collect_background_jobs_health_marks_degraded_without_worker():
    from backend.app.tasks.job_health import collect_background_jobs_health

    with patch(
        "backend.app.tasks.job_health.get_rq_mode_summary",
        return_value={"daily_jobs": "rq", "dunning": "thread"},
    ):
        with patch(
            "backend.app.tasks.job_health.get_worker_heartbeat_stats",
            return_value={"active": 0, "status": "ok"},
        ):
            with patch(
                "backend.app.tasks.job_health.get_job_status",
                return_value={"status": "unknown"},
            ):
                with patch("backend.app.tasks.job_health.task_queues_ready", return_value=True):
                    with patch("backend.app.tasks.job_health.get_queue_stats", return_value={}):
                        health = collect_background_jobs_health()

    assert health["anyRqMode"] is True
    assert "rq_worker_missing" in health["degraded"]
    assert health["healthy"] is False
