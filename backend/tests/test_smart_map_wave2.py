"""Smart Workforce Map wave-2: activity, nearest, anomalies, zone stats."""
from __future__ import annotations

import sqlite3
from contextlib import closing

from backend.app.platform.physical_operations._common import now_iso
from backend.app.platform.physical_operations.map_intelligence import (
    compute_zone_stats,
    display_status,
    evaluate_map_anomalies,
    find_nearest_workers,
    normalize_activity,
)
from backend.app.platform.workforce.presence_state import upsert_worker_activity


def test_normalize_and_display_status():
    assert normalize_activity("break") == "on_break"
    assert normalize_activity("task") == "on_task"
    assert display_status(geo_status="working", activity="on_break") == "on_break"
    assert display_status(geo_status="off_site", activity="working") == "off_site"
    assert display_status(geo_status="shift_ended", activity="on_break") == "shift_ended"


def test_zone_stats_and_nearest():
    zones = [{"id": "z1", "site_name": "Lager", "zone_kind": "warehouse", "color": "#8b5cf6"}]
    workers = [
        {
            "id": "a",
            "name": "Ali",
            "status": "working",
            "activity": "working",
            "role": "Elektriker",
            "lat": 52.52,
            "lng": 13.405,
            "currentZone": {"id": "z1", "name": "Lager", "kind": "warehouse"},
        },
        {
            "id": "b",
            "name": "Ben",
            "status": "on_break",
            "activity": "on_break",
            "role": "Lager",
            "lat": 52.5202,
            "lng": 13.4052,
            "currentZone": {"id": "z1", "name": "Lager", "kind": "warehouse"},
        },
        {
            "id": "c",
            "name": "Chris",
            "status": "working",
            "activity": "working",
            "role": "Sicherheit",
            "lat": 52.521,
            "lng": 13.41,
            "currentZone": None,
        },
    ]
    stats = compute_zone_stats(zones, workers)
    assert stats[0]["headcount"] == 2
    assert stats[0]["byStatus"]["working"] == 1
    assert stats[0]["byStatus"]["on_break"] == 1

    nearest = find_nearest_workers(workers, lat=52.52, lng=13.405, limit=3, role_query="elektr")
    assert len(nearest) == 1
    assert nearest[0]["id"] == "a"
    nearest_all = find_nearest_workers(workers, lat=52.52, lng=13.405, limit=5, exclude_break=True)
    assert all(w["id"] != "b" for w in nearest_all)


def test_anomalies_crowd_and_off_site():
    workers = [
        {
            "id": f"w{i}",
            "name": f"W{i}",
            "status": "working",
            "lastLocationAt": now_iso(),
            "site": "Produktion Nord",
            "currentZone": {"id": "z1", "name": "Lager Ost", "kind": "warehouse"},
            "lat": 52.52,
            "lng": 13.405,
        }
        for i in range(6)
    ]
    # Force age for off_site dwell by using old timestamp
    workers.append(
        {
            "id": "out1",
            "name": "Out",
            "status": "off_site",
            "lastLocationAt": "2020-01-01T10:00:00.000000Z",
            "site": "",
            "currentZone": None,
            "lat": 52.53,
            "lng": 13.42,
        }
    )
    zone_stats = [
        {
            "zoneId": "z1",
            "name": "Lager Ost",
            "kind": "warehouse",
            "headcount": 6,
            "byStatus": {"working": 6, "off_site": 0, "stale": 0, "on_break": 0, "on_task": 0},
        }
    ]
    anomalies = evaluate_map_anomalies(
        company_id="cmp-default",
        workers=workers,
        zone_stats=zone_stats,
    )
    codes = {a["code"] for a in anomalies}
    assert "map.zone_crowd" in codes
    assert "map.off_site_dwell" in codes


def test_upsert_worker_activity(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        assert upsert_worker_activity(
            db,
            worker_id="w-act-1",
            company_id="cmp-default",
            activity="on_break",
            note="Mittag",
        )
        db.commit()
        row = db.execute(
            "SELECT activity, activity_note FROM worker_presence_state WHERE worker_id = ?",
            ("w-act-1",),
        ).fetchone()
        assert row is not None
        assert row["activity"] == "on_break"
        assert "Mittag" in str(row["activity_note"] or "")
