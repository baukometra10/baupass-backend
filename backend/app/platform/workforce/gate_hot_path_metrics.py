"""Lightweight in-process counters for the gate hot path."""
from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_counters: dict[str, int] = {
    "taps_total": 0,
    "taps_ok": 0,
    "taps_denied": 0,
    "taps_duplicate": 0,
    "taps_error": 0,
    "taps_async_accepted": 0,
    "latency_sum_ms": 0,
    "latency_count": 0,
}
_started_at = time.time()


def record_gate_tap(*, status: int, processing_ms: int = 0, async_accepted: bool = False) -> None:
    with _lock:
        _counters["taps_total"] += 1
        if async_accepted:
            _counters["taps_async_accepted"] += 1
        elif status == 201:
            _counters["taps_ok"] += 1
        elif status in {202}:
            _counters["taps_duplicate"] += 1
        elif status >= 500:
            _counters["taps_error"] += 1
        elif status >= 400:
            _counters["taps_denied"] += 1
        if processing_ms > 0:
            _counters["latency_sum_ms"] += int(processing_ms)
            _counters["latency_count"] += 1


def snapshot_gate_hot_path_metrics() -> dict[str, Any]:
    with _lock:
        count = int(_counters["latency_count"] or 0)
        avg = int(round(_counters["latency_sum_ms"] / count)) if count else 0
        return {
            "tapsTotal": int(_counters["taps_total"]),
            "tapsOk": int(_counters["taps_ok"]),
            "tapsDenied": int(_counters["taps_denied"]),
            "tapsDuplicate": int(_counters["taps_duplicate"]),
            "tapsError": int(_counters["taps_error"]),
            "tapsAsyncAccepted": int(_counters["taps_async_accepted"]),
            "avgLatencyMs": avg,
            "uptimeSeconds": int(max(0, time.time() - _started_at)),
        }
