"""Live ops map coordinate resolution."""
from __future__ import annotations

import sqlite3
from contextlib import closing

from backend.app.platform.physical_operations._common import (
    is_fresh_live_location,
    is_usable_map_coordinate,
    now_iso,
    parse_device_coords_from_note,
    resolve_map_coordinates,
    resolve_worker_map_coordinates,
)
from backend.app.platform.workforce.presence_state import upsert_live_location


def test_is_usable_map_coordinate_rejects_null_island():
    assert is_usable_map_coordinate(0, 0) is False
    assert is_usable_map_coordinate(0.0, 0.0) is False


def test_is_usable_map_coordinate_accepts_berlin():
    assert is_usable_map_coordinate(52.52, 13.405) is True


def test_parse_device_coords_from_note():
    note = "Standort erkannt (GPS) | geofenceId=gf-1 | deviceLat=52.520008;deviceLng=13.404954"
    coords = parse_device_coords_from_note(note)
    assert coords is not None
    assert round(coords["lat"], 3) == 52.52
    assert round(coords["lng"], 3) == 13.405


def test_resolve_map_coordinates_ignores_zero_and_uses_geofence(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        db.execute(
            """
            INSERT INTO geofences (id, company_id, site_name, latitude, longitude, radius_meters, active, created_at)
            VALUES ('gf-berlin', 'cmp-default', 'Berlin Baustelle', 52.52, 13.405, 80, 1, datetime('now'))
            """
        )
        db.commit()
        coords = resolve_map_coordinates(
            db,
            "cmp-default",
            lat=0,
            lng=0,
            site="Berlin Baustelle",
            seed="worker-1",
        )
    assert coords is not None
    assert abs(coords["lat"] - 52.52) < 0.01
    assert abs(coords["lng"] - 13.405) < 0.01


def test_upsert_live_location_and_prefer_on_map(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        assert upsert_live_location(
            db,
            worker_id="w-live-1",
            company_id="cmp-default",
            lat=52.5211,
            lng=13.4062,
            accuracy_m=12,
            at=now_iso(),
        )
        db.commit()
        row = db.execute(
            "SELECT last_lat, last_lng, last_location_at FROM worker_presence_state WHERE worker_id = ?",
            ("w-live-1",),
        ).fetchone()
        assert row is not None
        assert abs(float(row["last_lat"]) - 52.5211) < 0.0001
        assert abs(float(row["last_lng"]) - 13.4062) < 0.0001
        assert is_fresh_live_location(row["last_location_at"])

        coords = resolve_worker_map_coordinates(
            db,
            "cmp-default",
            {
                "id": "w-live-1",
                "site": "Berlin Baustelle",
                "site_latitude": 52.52,
                "site_longitude": 13.405,
                "last_lat": row["last_lat"],
                "last_lng": row["last_lng"],
                "last_location_at": row["last_location_at"],
                "last_note": "",
            },
        )
    assert coords is not None
    assert coords["source"] == "live"
    assert abs(coords["lat"] - 52.5211) < 0.0001
    assert abs(coords["lng"] - 13.4062) < 0.0001


def test_resolve_prefers_stale_live_gps_over_zone_anchor(client_and_db):
    """Pins should stay at last phone GPS instead of snapping to geofence center."""
    from datetime import datetime, timedelta, timezone

    _client, db_path = client_and_db
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        db.execute(
            """
            INSERT INTO geofences (id, company_id, site_name, latitude, longitude, radius_meters, active, created_at)
            VALUES ('gf-anchor', 'cmp-default', 'Hassoweg', 52.52, 13.405, 80, 1, datetime('now'))
            """
        )
        db.commit()
        coords = resolve_worker_map_coordinates(
            db,
            "cmp-default",
            {
                "id": "w-stale-live",
                "site": "Hassoweg",
                "site_latitude": 52.52,
                "site_longitude": 13.405,
                "last_lat": 52.4801,
                "last_lng": 13.4502,
                "last_location_at": old,
                "last_note": "",
            },
        )
    assert coords is not None
    assert coords["source"] == "live"
    assert abs(coords["lat"] - 52.4801) < 0.0001
    assert abs(coords["lng"] - 13.4502) < 0.0001
    assert is_fresh_live_location(old) is False


def test_resolve_worker_map_coordinates_uses_exact_checkin_gps(client_and_db):
    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        coords = resolve_worker_map_coordinates(
            db,
            "cmp-default",
            {
                "id": "w-checkin",
                "site": "Berlin Baustelle",
                "last_lat": None,
                "last_lng": None,
                "last_location_at": "",
                "last_note": "GPS | deviceLat=52.520500;deviceLng=13.405500",
            },
        )
    assert coords is not None
    assert coords["source"] == "checkin"
    assert abs(coords["lat"] - 52.5205) < 0.0001
    assert abs(coords["lng"] - 13.4055) < 0.0001


def test_derive_status_and_zone_and_trail(client_and_db):
    from backend.app.platform.physical_operations.location_trail import (
        derive_worker_map_status,
        get_worker_trail,
        maybe_record_location_sample,
        resolve_containing_zone,
    )

    zones = [
        {
            "id": "gf-prod",
            "site_name": "Produktion",
            "latitude": 52.52,
            "longitude": 13.405,
            "radius_meters": 80,
            "zone_kind": "production",
            "color": "#f59e0b",
        }
    ]
    inside = resolve_containing_zone(52.5201, 13.4051, zones)
    assert inside is not None
    assert inside["zone_kind"] == "production"
    outside = resolve_containing_zone(52.53, 13.42, zones)
    assert outside is None

    assert (
        derive_worker_map_status(
            position_source="live",
            last_location_at=now_iso(),
            inside_zone=True,
        )
        == "working"
    )
    assert (
        derive_worker_map_status(
            position_source="live",
            last_location_at=now_iso(),
            inside_zone=False,
        )
        == "off_site"
    )
    assert (
        derive_worker_map_status(
            position_source="anchor",
            last_location_at="",
            inside_zone=True,
        )
        == "working"
    )
    assert (
        derive_worker_map_status(
            position_source="anchor",
            last_location_at="",
            inside_zone=False,
        )
        == "stale"
    )

    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        assert maybe_record_location_sample(
            db,
            worker_id="w-trail-1",
            company_id="cmp-default",
            lat=52.5201,
            lng=13.4051,
            accuracy_m=8,
            geofence_id="gf-prod",
            zone_kind="production",
            at=now_iso(),
            min_interval_seconds=0,
            min_move_meters=0,
        )
        # Throttle: identical immediate sample should be skipped with default thresholds
        assert (
            maybe_record_location_sample(
                db,
                worker_id="w-trail-1",
                company_id="cmp-default",
                lat=52.5201,
                lng=13.4051,
                accuracy_m=8,
                geofence_id="gf-prod",
                zone_kind="production",
                at=now_iso(),
            )
            is False
        )
        # Move enough meters -> new sample
        assert maybe_record_location_sample(
            db,
            worker_id="w-trail-1",
            company_id="cmp-default",
            lat=52.5203,
            lng=13.4054,
            accuracy_m=8,
            geofence_id="gf-prod",
            zone_kind="production",
            at=now_iso(),
            min_interval_seconds=0,
            min_move_meters=5,
        )
        db.commit()
        trail = get_worker_trail(db, company_id="cmp-default", worker_id="w-trail-1")
        assert trail["count"] >= 2
        assert trail["points"][0]["zoneKind"] in ("production", "")


def test_build_live_ops_map_includes_status(client_and_db):
    from backend.app.platform.physical_operations.live_map import build_live_ops_map

    _client, db_path = client_and_db
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        try:
            db.execute(
                """
                INSERT INTO geofences (
                    id, company_id, site_name, latitude, longitude, radius_meters, active, zone_kind, color, created_at
                ) VALUES ('gf-swm', 'cmp-default', 'Lager', 52.52, 13.405, 100, 1, 'warehouse', '#8b5cf6', datetime('now'))
                """
            )
        except sqlite3.OperationalError:
            db.execute(
                """
                INSERT INTO geofences (id, company_id, site_name, latitude, longitude, radius_meters, active, created_at)
                VALUES ('gf-swm', 'cmp-default', 'Lager', 52.52, 13.405, 100, 1, datetime('now'))
                """
            )
        db.commit()
        payload = build_live_ops_map(db, "cmp-default")
    assert "statusCounts" in payload
    assert "geofences" in payload
    assert payload["geofences"]
    assert payload["geofences"][0].get("zone_kind") in (
        "warehouse",
        "site",
        "production",
        "admin",
        "maintenance",
        "lab",
        "other",
    )
