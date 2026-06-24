"""Geofence distance accuracy adjustments."""
from __future__ import annotations

from backend import server


def test_geofence_radius_allows_accuracy_buffer():
    allowed = server._geofence_radius_with_accuracy_buffer(20, 10)
    assert allowed == 30


def test_worker_within_site_geofence_uses_accuracy_buffer():
    assert server.worker_within_site_geofence(28, 20, 10) is True
    assert server.worker_within_site_geofence(35, 20, 10) is False


def test_measure_worker_site_distance_reports_raw_distance(worker_client):
    with server.app.app_context():
        db = server.get_db()
        db.execute(
            """
            INSERT INTO companies (id, name, contact, plan, status)
            VALUES ('cmp-geo-test', 'Geo Test', '', 'starter', 'active')
            """
        )
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, status, photo_data,
                badge_id, badge_id_lookup, badge_pin_hash, physical_card_id,
                site_latitude, site_longitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wrk-geo-test",
                "cmp-geo-test",
                "Geo",
                "Worker",
                "INS-GEO",
                "worker",
                "arbeiter",
                "Test Site",
                "2099-12-31",
                "aktiv",
                "",
                "BP-GEO-TEST",
                "BP-GEO-TEST",
                server.generate_password_hash("1234"),
                None,
                52.52,
                13.405,
            ),
        )
        db.commit()
        worker = db.execute("SELECT * FROM workers WHERE id = ?", ("wrk-geo-test",)).fetchone()

    measured = server.measure_worker_site_distance(
        db,
        worker,
        {"latitude": 52.52, "longitude": 13.405, "accuracy": 8},
    )
    assert measured is not None
    assert measured["distanceMeters"] == 0
    assert measured["onSite"] is True
    assert measured["accuracyMeters"] == 8
    assert measured["allowedRadiusMeters"] == 28


def test_measure_worker_site_distance_rejects_inaccurate_reading(worker_client):
    with server.app.app_context():
        db = server.get_db()
        worker = db.execute("SELECT * FROM workers WHERE id = ?", ("wrk-geo-test",)).fetchone()

    try:
        server.measure_worker_site_distance(
            db,
            worker,
            {"latitude": 52.52, "longitude": 13.405, "accuracy": 120},
        )
        raised = False
    except ValueError as error:
        raised = True
        assert str(error) == "worker_geolocation_inaccurate"
    assert raised
