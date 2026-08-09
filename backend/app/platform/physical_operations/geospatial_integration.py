"""
Integration layer — Connect GeospatialOptimizer with existing location, camera, and police modules.

This module provides high-level functions that replace existing implementations with
optimized versions using Bounding Box pre-filtering and intelligent caching.
"""

from __future__ import annotations

from typing import Any

try:
    from .geospatial_optimizer import GeoPoint, get_optimizer, haversine_meters
except ImportError:
    from geospatial_optimizer import GeoPoint, get_optimizer, haversine_meters

# Re-export for older imports
_compat_haversine = haversine_meters


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
    """
    optimizer = get_optimizer()
    center = GeoPoint(worker_lat, worker_lng, id="worker_location")

    result = optimizer.find_nearest_in_db(
        db,
        center,
        table="cameras",
        lat_col="latitude",
        lng_col="longitude",
        limit=limit,
        radius_meters=search_radius_meters,
        extra_where="company_id = ?",
        extra_params=(company_id,),
        cache_key=f"cameras|{worker_lat:.3f}|{worker_lng:.3f}|{company_id}",
    )

    return result.points


def find_nearest_workers_optimized(
    workers: list[dict[str, Any]],
    *,
    center_lat: float,
    center_lng: float,
    limit: int = 5,
    search_radius_meters: float = 5000.0,
    role_filter: str = "",
    exclude_on_break: bool = True,
    return_meta: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], dict[str, Any]]:
    """Find nearest workers using optimized Bounding Box / grid search."""
    from .map_intelligence import find_nearest_workers

    return find_nearest_workers(
        workers,
        lat=center_lat,
        lng=center_lng,
        limit=limit,
        role_query=role_filter,
        exclude_break=exclude_on_break,
        radius_meters=search_radius_meters,
        return_meta=return_meta,
    )


def find_nearest_zones_optimized(
    zones: list[dict[str, Any]],
    *,
    worker_lat: float,
    worker_lng: float,
    limit: int = 3,
    search_radius_meters: float = 300.0,
) -> list[dict[str, Any]]:
    """Find nearest geofence zones (smart zones/geofences)."""
    optimizer = get_optimizer()
    center = GeoPoint(worker_lat, worker_lng, id="worker")

    normalized = []
    for z in zones or []:
        item = dict(z)
        if "lat" not in item and item.get("latitude") is not None:
            item["lat"] = item.get("latitude")
        if "lng" not in item and item.get("longitude") is not None:
            item["lng"] = item.get("longitude")
        normalized.append(item)

    result = optimizer.find_nearest(
        center,
        normalized,
        limit=limit,
        radius_meters=search_radius_meters,
        lat_key="lat",
        lng_key="lng",
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
    """Find nearest police station using database-level geospatial optimization."""
    optimizer = get_optimizer()
    center = GeoPoint(incident_lat, incident_lng, id="incident")
    radius_meters = search_radius_km * 1000

    extra_where = ""
    extra_params: tuple[Any, ...] = ()
    if country:
        extra_where = "country_code = ?"
        extra_params = (country,)

    result = optimizer.find_nearest_in_db(
        db,
        center,
        table="police_stations",
        lat_col="latitude",
        lng_col="longitude",
        limit=1,
        radius_meters=radius_meters,
        extra_where=extra_where,
        extra_params=extra_params,
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
    return get_optimizer().get_metrics()


def clear_geospatial_cache() -> None:
    """Clear all geospatial cache."""
    get_optimizer().clear_cache()


def reset_geospatial_metrics() -> None:
    """Reset geospatial performance metrics."""
    get_optimizer().reset_metrics()
