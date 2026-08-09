"""
Comprehensive tests for GeospatialOptimizer — accuracy, performance, caching, and edge cases.
"""

import math
import pytest
import time
from typing import Any

from backend.app.platform.physical_operations.geospatial_optimizer import (
    BoundingBox,
    GeoPoint,
    GeospatialOptimizer,
    SpatialGridIndex,
    haversine_meters,
    get_optimizer,
    point_in_circle_bbox_then_haversine,
)
from backend.app.platform.physical_operations.geospatial_integration import (
    find_nearest_cameras_optimized,
    find_nearest_workers_optimized,
    find_nearest_zones_optimized,
)


class TestHaversine:
    """Test Haversine distance calculation."""

    def test_same_point(self):
        """Distance to same point should be 0."""
        dist = haversine_meters(52.5, 13.4, 52.5, 13.4)
        assert dist < 1.0  # Allow 1 meter tolerance

    def test_known_distance_berlin_paris(self):
        """Berlin to Paris is approximately 877 km."""
        berlin = (52.52, 13.405)
        paris = (48.856, 2.353)
        dist = haversine_meters(*berlin, *paris)
        expected = 877_000  # 877 km in meters
        assert abs(dist - expected) < 10_000  # Within 10 km tolerance

    def test_distance_symmetry(self):
        """Distance from A to B should equal B to A."""
        d1 = haversine_meters(52.5, 13.4, 48.8, 2.3)
        d2 = haversine_meters(48.8, 2.3, 52.5, 13.4)
        assert abs(d1 - d2) < 1.0

    def test_antipodal_points(self):
        """Distance between antipodal points is ~20,000 km."""
        dist = haversine_meters(0, 0, 0, 180)
        expected = math.pi * 6_371_000  # ~20,015,086 meters
        assert abs(dist - expected) < 10_000


class TestGeoPoint:
    """Test GeoPoint data class."""

    def test_geopoint_creation(self):
        point = GeoPoint(52.5, 13.4, id="test", name="Berlin")
        assert point.lat == 52.5
        assert point.lng == 13.4
        assert point.id == "test"
        assert point.name == "Berlin"

    def test_geopoint_distance(self):
        p1 = GeoPoint(52.5, 13.4, id="berlin")
        p2 = GeoPoint(52.6, 13.5, id="nearby")
        dist = p1.distance_to(p2)
        assert 10_000 < dist < 20_000  # ~10-20 km

    def test_geopoint_equality(self):
        p1 = GeoPoint(52.5, 13.4)
        p2 = GeoPoint(52.5, 13.4)
        p3 = GeoPoint(52.6, 13.5)
        assert p1 == p2
        assert p1 != p3

    def test_geopoint_hash(self):
        """GeoPoints should be hashable and work in sets."""
        p1 = GeoPoint(52.5, 13.4)
        p2 = GeoPoint(52.5, 13.4)
        p3 = GeoPoint(52.6, 13.5)
        point_set = {p1, p2, p3}
        assert len(point_set) == 2  # p1 and p2 are equal


class TestBoundingBox:
    """Test BoundingBox creation and operations."""

    def test_bounding_box_around_point(self):
        """Create bounding box around a point."""
        bbox = BoundingBox.around_point(52.5, 13.4, 1000)  # 1 km radius
        assert bbox.min_lat < 52.5 < bbox.max_lat
        assert bbox.min_lng < 13.4 < bbox.max_lng

    def test_bounding_box_contains(self):
        """Test if bounding box contains points."""
        bbox = BoundingBox.around_point(52.5, 13.4, 1000)
        center = GeoPoint(52.5, 13.4)
        nearby = GeoPoint(52.501, 13.401)
        far = GeoPoint(53.0, 14.0)

        assert bbox.contains(center)
        assert bbox.contains(nearby)
        assert not bbox.contains(far)

    def test_bounding_box_sql_where(self):
        """Test SQL WHERE clause generation."""
        bbox = BoundingBox(51.0, 53.0, 12.0, 15.0)
        where = bbox.to_sql_where("lat", "lng")
        assert "lat BETWEEN" in where
        assert "lng BETWEEN" in where
        assert "51.0" in where and "53.0" in where
        clause = bbox.to_sql_clause("lat", "lng")
        assert clause == "lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?"

    def test_bounding_box_sql_params(self):
        """Test SQL parameter generation."""
        bbox = BoundingBox(51.0, 53.0, 12.0, 15.0)
        params = bbox.to_sql_params()
        assert params == (51.0, 53.0, 12.0, 15.0)
        as_dict = bbox.to_sql_params_dict()
        assert as_dict["min_lat"] == 51.0
        assert as_dict["max_lat"] == 53.0
        assert as_dict["min_lng"] == 12.0
        assert as_dict["max_lng"] == 15.0

class TestGeospatialOptimizer:
    """Test GeospatialOptimizer main functionality."""

    @pytest.fixture
    def optimizer(self):
        """Create fresh optimizer for each test."""
        return GeospatialOptimizer(cache_size=100, cache_ttl_seconds=60)

    def test_find_nearest_single_candidate(self, optimizer):
        """Test finding nearest with single candidate."""
        center = GeoPoint(52.5, 13.4, id="center")
        candidates = [
            {
                "id": "cam1",
                "name": "Camera 1",
                "lat": 52.501,
                "lng": 13.401,
            }
        ]
        result = optimizer.find_nearest(center, candidates, limit=1)
        assert len(result.points) == 1
        assert result.points[0]["id"] == "cam1"
        assert result.points[0]["distanceMeters"] < 200

    def test_find_nearest_multiple_candidates_sorting(self, optimizer):
        """Test that results are sorted by distance."""
        center = GeoPoint(52.5, 13.4, id="center")
        candidates = [
            {"id": "far", "name": "Far", "lat": 53.0, "lng": 14.0},
            {"id": "near", "name": "Near", "lat": 52.501, "lng": 13.401},
            {"id": "medium", "name": "Medium", "lat": 52.51, "lng": 13.41},
        ]
        result = optimizer.find_nearest(center, candidates, limit=3, radius_meters=200_000)
        distances = [p["distanceMeters"] for p in result.points]
        assert distances == sorted(distances)  # Sorted ascending

    def test_find_nearest_radius_filtering(self, optimizer):
        """Test that radius_meters filters out distant candidates."""
        center = GeoPoint(52.5, 13.4, id="center")
        candidates = [
            {"id": "near", "name": "Near", "lat": 52.501, "lng": 13.401},  # ~110m
            {"id": "far", "name": "Far", "lat": 53.0, "lng": 14.0},  # ~80 km
        ]
        result = optimizer.find_nearest(center, candidates, limit=10, radius_meters=1000)
        assert len(result.points) == 1
        assert result.points[0]["id"] == "near"

    def test_find_nearest_with_filter_fn(self, optimizer):
        """Test filtering with custom predicate."""
        center = GeoPoint(52.5, 13.4, id="center")
        candidates = [
            {"id": "cam1", "name": "Camera 1", "lat": 52.501, "lng": 13.401, "online": True},
            {"id": "cam2", "name": "Camera 2", "lat": 52.502, "lng": 13.402, "online": False},
            {"id": "cam3", "name": "Camera 3", "lat": 52.503, "lng": 13.403, "online": True},
        ]

        def online_only(cand):
            return cand.get("online") is True

        result = optimizer.find_nearest(center, candidates, limit=10, filter_fn=online_only, radius_meters=10_000)
        assert len(result.points) == 2
        assert all(p["online"] is True for p in result.points)

    def test_caching_works(self, optimizer):
        """Test that caching returns cached results."""
        center = GeoPoint(52.5, 13.4, id="center")
        candidates = [
            {"id": f"cam{i}", "name": f"Camera {i}", "lat": 52.5 + i * 0.001, "lng": 13.4}
            for i in range(10)
        ]

        # First call — not cached
        result1 = optimizer.find_nearest(center, candidates, limit=5, cache_key="test_cache")
        assert result1.cache_hit is False

        # Second call with same cache key — should be cached
        result2 = optimizer.find_nearest(center, candidates, limit=5, cache_key="test_cache")
        assert result2.cache_hit is True
        assert result2.points == result1.points

    def test_cache_expiration(self, optimizer):
        """Test that cache expires after TTL."""
        optimizer.cache_ttl_seconds = 1  # 1 second TTL
        center = GeoPoint(52.5, 13.4, id="center")
        candidates = [{"id": "cam1", "lat": 52.501, "lng": 13.401}]

        result1 = optimizer.find_nearest(center, candidates, cache_key="expire_test")
        assert result1.cache_hit is False

        time.sleep(1.1)  # Wait for cache to expire

        result2 = optimizer.find_nearest(center, candidates, cache_key="expire_test")
        assert result2.cache_hit is False  # Cache expired

    def test_metrics_tracking(self, optimizer):
        """Test that metrics are tracked correctly."""
        center = GeoPoint(52.5, 13.4, id="center")
        candidates = [{"id": "cam1", "lat": 52.501, "lng": 13.401}]

        optimizer.find_nearest(center, candidates, limit=1)
        metrics = optimizer.get_metrics()

        assert metrics["total_queries"] == 1
        assert metrics["total_bbox_filters"] == 1
        assert metrics["total_haversine_calls"] == 1

    def test_limit_enforcement(self, optimizer):
        """Test that limit is enforced."""
        center = GeoPoint(52.5, 13.4, id="center")
        candidates = [
            {"id": f"cam{i}", "lat": 52.5 + i * 0.0001, "lng": 13.4}
            for i in range(50)
        ]
        result = optimizer.find_nearest(center, candidates, limit=5, radius_meters=100_000)
        assert len(result.points) <= 5

    def test_limit_max_capped_at_100(self, optimizer):
        """Test that limit is capped at 100."""
        center = GeoPoint(52.5, 13.4, id="center")
        candidates = [
            {"id": f"cam{i}", "lat": 52.5 + i * 0.00001, "lng": 13.4}
            for i in range(200)
        ]
        result = optimizer.find_nearest(center, candidates, limit=500, radius_meters=100_000)
        assert len(result.points) <= 100


class TestGeospatialIntegration:
    """Test integration functions."""

    def test_find_nearest_workers_optimized(self):
        """Test worker finding integration."""
        workers = [
            {
                "id": "w1",
                "name": "Alice",
                "role": "warehouse",
                "status": "working",
                "activity": "working",
                "lat": 52.501,
                "lng": 13.401,
            },
            {
                "id": "w2",
                "name": "Bob",
                "role": "admin",
                "status": "on_break",
                "activity": "on_break",
                "lat": 52.502,
                "lng": 13.402,
            },
            {
                "id": "w3",
                "name": "Charlie",
                "role": "warehouse",
                "status": "working",
                "activity": "working",
                "lat": 52.510,
                "lng": 13.410,
            },
        ]

        result = find_nearest_workers_optimized(
            workers,
            center_lat=52.5,
            center_lng=13.4,
            limit=2,
            exclude_on_break=True,
        )

        assert len(result) == 2
        # Bob should be excluded (on_break)
        assert all(w["id"] != "w2" for w in result)
        # Results should be sorted by distance
        distances = [w["distanceMeters"] for w in result]
        assert distances == sorted(distances)

    def test_find_nearest_workers_with_role_filter(self):
        """Test worker finding with role filter."""
        workers = [
            {
                "id": "w1",
                "name": "Alice",
                "role": "warehouse_manager",
                "status": "working",
                "lat": 52.501,
                "lng": 13.401,
            },
            {
                "id": "w2",
                "name": "Bob",
                "role": "admin",
                "status": "working",
                "lat": 52.502,
                "lng": 13.402,
            },
        ]

        result = find_nearest_workers_optimized(
            workers,
            center_lat=52.5,
            center_lng=13.4,
            limit=10,
            role_filter="warehouse",
        )

        assert len(result) == 1
        assert result[0]["id"] == "w1"


class TestSpatialPrimitives:
    def test_bbox_rejects_before_haversine(self):
        inside, dist = point_in_circle_bbox_then_haversine(52.5, 13.4, 52.5, 13.4, 100)
        assert inside is True
        assert dist is not None and dist < 1

        outside, dist2 = point_in_circle_bbox_then_haversine(53.0, 14.0, 52.5, 13.4, 100)
        assert outside is False
        assert dist2 is None

    def test_grid_nearest_matches_bruteforce_order(self):
        center = GeoPoint(52.5, 13.4)
        candidates = [
            {"id": f"w{i}", "lat": 52.5 + (i % 20) * 0.001, "lng": 13.4 + (i // 20) * 0.001}
            for i in range(60)
        ]
        opt = GeospatialOptimizer()
        with_grid = opt.find_nearest(center, candidates, limit=5, radius_meters=5_000, use_grid=True)
        no_grid = opt.find_nearest(center, candidates, limit=5, radius_meters=5_000, use_grid=False)
        assert [p["id"] for p in with_grid.points] == [p["id"] for p in no_grid.points]
        assert with_grid.method == "grid+bbox+haversine"

    def test_spatial_grid_query_bbox(self):
        grid = SpatialGridIndex(cell_size_meters=100, reference_lat=52.5)
        grid.build(
            [
                {"id": "a", "lat": 52.5001, "lng": 13.4001},
                {"id": "b", "lat": 53.0, "lng": 14.0},
            ]
        )
        hits = grid.query_bbox(BoundingBox.around_point(52.5, 13.4, 200))
        assert any(h["id"] == "a" for h in hits)
        assert all(h["id"] != "b" for h in hits)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_coordinates_ignored(self):
        """Test that invalid coordinates are gracefully ignored."""
        optimizer = GeospatialOptimizer()
        center = GeoPoint(52.5, 13.4, id="center")
        candidates = [
            {"id": "valid", "lat": 52.501, "lng": 13.401},
            {"id": "invalid1", "lat": None, "lng": 13.401},
            {"id": "invalid2", "lat": "not_a_number", "lng": 13.401},
            {"id": "invalid3", "lat": 52.501, "lng": None},
        ]
        result = optimizer.find_nearest(center, candidates, limit=10)
        assert len(result.points) == 1
        assert result.points[0]["id"] == "valid"

    def test_empty_candidates_list(self):
        """Test behavior with empty candidates."""
        optimizer = GeospatialOptimizer()
        center = GeoPoint(52.5, 13.4, id="center")
        result = optimizer.find_nearest(center, [], limit=5)
        assert len(result.points) == 0

    def test_very_large_search_radius(self):
        """Test with very large search radius."""
        optimizer = GeospatialOptimizer()
        center = GeoPoint(52.5, 13.4, id="center")
        candidates = [
            {"id": "cam1", "lat": 52.5, "lng": 13.4},  # Center
            {"id": "cam2", "lat": 0, "lng": 0},  # Antipodal
        ]
        result = optimizer.find_nearest(center, candidates, radius_meters=20_000_000)
        assert len(result.points) == 2  # Both should be found


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
