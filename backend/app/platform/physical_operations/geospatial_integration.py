"""
Integration layer — Connect GeospatialOptimizer with existing location, camera, and police modules.

This module provides high-level functions that replace existing implementations with
optimized versions using Bounding Box pre-filtering and intelligent caching.
"""

from __future__ import annotations

from typing import Any

try:
    from .geospatial_optimizer import GeoPoint, GeospatialOptimizer, get_optimizer
except ImportError:
    from geospatial_optimizer import GeoPoint, GeospatialOptimizer, get_optimizer

try:
    from .location_trail import haversine_meters as _compat_haversine
except ImportError:
    def _compat_haversine(lat1, lng1, lat2, lng2):
        pass  # Unused for now


def find_nearest_cameras_optimized(
    db,
    *,
    worker_lat: float,
    worker_lng: float,
    company_id: str,
    limit: int = 5,
    search_radius_meters: float = 500.0,
) -> list[dict[str, Any]]:
    """
    Find nearest cameras to worker using Bounding Box optimization.

    Replaces naive iteration over all cameras with:
    1. SQL Bounding Box filter → typically 90% reduction
    2. Haversine only on filtered results
    3. LRU caching with TTL

    Args:
        db: Database connection
        worker_lat: Worker latitude
        worker_lng: Worker longitude
        company_id: Company ID for filtering
        limit: Max cameras to return
        search_radius_meters: Search radius in meters

    Returns:
        List of cameras sorted by distance
    """
    optimizer = get_optimizer()
    center = GeoPoint(worker_lat, worker_lng, id="worker_location")

    # Use database-level optimization for better performance
    result = optimizer.find_nearest_in_db(
        db,
        center,
        table="cameras",
        lat_col="latitude",
        lng_col="longitude",
        limit=limit,
        radius_meters=search_radius_meters,
        where_clause="company_id = ?",
        where_params={"company_id": company_id},
        cache_key=f"cameras|{worker_lat:.3f}|{worker_lng:.3f}|{company_id}",
    )

    return result.points


def find_nearest_workers_optimized(
    workers: list[dict[str, Any]],
    *,
    center_lat: float,
    center_lng: float,
    limit: int = 5,
    search_radius_meters: float = 1000.0,
    role_filter: str = "",
    exclude_on_break: bool = True,
) -> list[dict[str, Any]]:
    """
    Find nearest workers using optimized Bounding Box search.

    Replaces map_intelligence.find_nearest_workers with:
    1. Bounding Box pre-filter (eliminates ~90% of workers)
    2. Haversine on remaining workers only
    3. Smart caching

    Args:
        workers: List of worker dicts (must have 'lat', 'lng', 'id', 'name', 'role')
        center_lat: Search center latitude
        center_lng: Search center longitude
        limit: Max workers to return
        search_radius_meters: Search radius in meters
        role_filter: Optional role filter (substring match, case-insensitive)
        exclude_on_break: If True, exclude workers on break

    Returns:
        List of workers sorted by distance
    """
    optimizer = get_optimizer()
    center = GeoPoint(center_lat, center_lng, id="search_center")

    def filter_fn(worker: dict) -> bool:
        """Filter function for workers."""
        # Exclude workers on break
        if exclude_on_break:
            status = str(worker.get("status") or "")
            activity = str(worker.get("activity") or "")
            if status == "on_break" or activity == "on_break":
                return False
        # Exclude workers with ended shift
        if str(worker.get("status") or "") == "shift_ended":
            return False
        # Role filter (if provided)
        if role_filter:
            role = str(worker.get("role") or "").lower()
            if role_filter.lower() not in role:
                return False
        return True

    result = optimizer.find_nearest(
        center,
        workers,
        limit=limit,
        radius_meters=search_radius_meters,
        filter_fn=filter_fn,
        cache_key=f"workers|{center_lat:.3f}|{center_lng:.3f}|{role_filter or 'all'}",
    )

    return result.points


def find_nearest_zones_optimized(
    zones: list[dict[str, Any]],
    *,
    worker_lat: float,
    worker_lng: float,
    limit: int = 3,
    search_radius_meters: float = 300.0,
) -> list[dict[str, Any]]:
    """
    Find nearest geofence zones (smart zones/geofences).

    Args:
        zones: List of zone dicts (must have 'latitude', 'longitude', 'id', 'site_name')
        worker_lat: Worker latitude
        worker_lng: Worker longitude
        limit: Max zones to return
        search_radius_meters: Search radius in meters

    Returns:
        List of zones sorted by distance
    """
    optimizer = get_optimizer()
    center = GeoPoint(worker_lat, worker_lng, id="worker")

    result = optimizer.find_nearest(
        center,
        zones,
        limit=limit,
        radius_meters=search_radius_meters,
        cache_key=f"zones|{worker_lat:.3f}|{worker_lng:.3f}",
    )

    return result.points


def find_nearest_police_station_optimized(
    db,
    *,
    incident_lat: float,
    incident_lng: float,
    country: str = "",
    search_radius_km: float = 50.0,
) -> dict[str, Any] | None:
    """
    Find nearest police station using database-level geospatial optimization.

    Args:
        db: Database connection
        incident_lat: Incident latitude
        incident_lng: Incident longitude
        country: Country code (for filtering)
        search_radius_km: Search radius in kilometers

    Returns:
        Nearest police station dict or None
    """
    optimizer = get_optimizer()
    center = GeoPoint(incident_lat, incident_lng, id="incident")

    # Convert km to meters
    radius_meters = search_radius_km * 1000

    # Build WHERE clause
    where_clause = ""
    where_params = {}
    if country:
        where_clause = "country_code = ?"
        where_params = {"country_code": country}

    result = optimizer.find_nearest_in_db(
        db,
        center,
        table="police_stations",
        lat_col="latitude",
        lng_col="longitude",
        limit=1,
        radius_meters=radius_meters,
        where_clause=where_clause,
        where_params=where_params,
        cache_key=f"police|{incident_lat:.2f}|{incident_lng:.2f}|{country}",
    )

    if result.points:
        station = result.points[0]
        return {
            "id": station.get("id"),
            "name": station.get("name"),
            "phone": station.get("phone"),
            "address": station.get("address"),
            "lat": station.get("lat"),
            "lng": station.get("lng"),
            "distanceKm": round(station.get("distanceMeters", 0) / 1000, 1),
        }
    return None


def get_geospatial_metrics() -> dict[str, Any]:
    """Get performance metrics from the global optimizer."""
    optimizer = get_optimizer()
    return optimizer.get_metrics()


def clear_geospatial_cache() -> None:
    """Clear all geospatial cache."""
    optimizer = get_optimizer()
    optimizer.clear_cache()


def reset_geospatial_metrics() -> None:
    """Reset geospatial performance metrics."""
    optimizer = get_optimizer()
    optimizer.reset_metrics()
