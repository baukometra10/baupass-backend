"""Live ops map coordinate resolution."""
from __future__ import annotations

from backend.app.platform.physical_operations._common import (
    is_usable_map_coordinate,
    parse_device_coords_from_note,
    resolve_map_coordinates,
)


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
    client, db = client_and_db
    db.execute(
        """
        INSERT INTO geofences (id, company_id, site_name, latitude, longitude, radius_meters, active)
        VALUES ('gf-berlin', 'cmp-default', 'Berlin Baustelle', 52.52, 13.405, 80, 1)
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
