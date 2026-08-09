"""
Geospatial engine for Live Workforce Map: Bounding Box + Spatial Grid Index + Haversine.

No external deps (stdlib only). Used by ops live-map nearest, zone match, and camera match.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

EARTH_RADIUS_METERS = 6_371_000.0


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in meters (Haversine)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(min(1.0, a)))


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lng: float
    id: str = ""
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    def distance_to(self, other: "GeoPoint") -> float:
        return haversine_meters(self.lat, self.lng, other.lat, other.lng)


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned geographic bounding box (lat/lng degrees)."""

    min_lat: float
    max_lat: float
    min_lng: float
    max_lng: float

    @classmethod
    def around_point(cls, lat: float, lng: float, radius_meters: float) -> "BoundingBox":
        radius_meters = max(0.0, float(radius_meters))
        lat_offset = (radius_meters / EARTH_RADIUS_METERS) * (180.0 / math.pi)
        cos_lat = math.cos(math.radians(lat))
        if abs(cos_lat) < 1e-6:
            lng_offset = 180.0
        else:
            lng_offset = (radius_meters / EARTH_RADIUS_METERS) * (180.0 / math.pi) / cos_lat
        return cls(
            min_lat=max(-90.0, lat - lat_offset),
            max_lat=min(90.0, lat + lat_offset),
            min_lng=max(-180.0, lng - lng_offset),
            max_lng=min(180.0, lng + lng_offset),
        )

    @classmethod
    def from_circle(cls, lat: float, lng: float, radius_meters: float) -> "BoundingBox":
        return cls.around_point(lat, lng, radius_meters)

    @classmethod
    def from_points(cls, points: Iterable[tuple[float, float]], *, pad_meters: float = 0.0) -> "BoundingBox | None":
        pts = list(points)
        if not pts:
            return None
        lats = [p[0] for p in pts]
        lngs = [p[1] for p in pts]
        box = cls(min(lats), max(lats), min(lngs), max(lngs))
        if pad_meters > 0:
            mid_lat = (box.min_lat + box.max_lat) / 2.0
            mid_lng = (box.min_lng + box.max_lng) / 2.0
            pad = cls.around_point(mid_lat, mid_lng, pad_meters)
            return cls(
                min_lat=min(box.min_lat, pad.min_lat),
                max_lat=max(box.max_lat, pad.max_lat),
                min_lng=min(box.min_lng, pad.min_lng),
                max_lng=max(box.max_lng, pad.max_lng),
            )
        return box

    def contains(self, point: GeoPoint) -> bool:
        return self.contains_lat_lng(point.lat, point.lng)

    def contains_lat_lng(self, lat: float, lng: float) -> bool:
        return self.min_lat <= lat <= self.max_lat and self.min_lng <= lng <= self.max_lng

    def intersects(self, other: "BoundingBox") -> bool:
        return not (
            self.max_lat < other.min_lat
            or self.min_lat > other.max_lat
            or self.max_lng < other.min_lng
            or self.min_lng > other.max_lng
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "minLat": self.min_lat,
            "maxLat": self.max_lat,
            "minLng": self.min_lng,
            "maxLng": self.max_lng,
        }

    def to_sql_params(self) -> tuple[float, float, float, float]:
        """Ordered params: min_lat, max_lat, min_lng, max_lng for SQLite placeholders."""
        return (self.min_lat, self.max_lat, self.min_lng, self.max_lng)

    def to_sql_params_dict(self) -> dict[str, float]:
        return {
            "min_lat": self.min_lat,
            "max_lat": self.max_lat,
            "min_lng": self.min_lng,
            "max_lng": self.max_lng,
        }

    def to_sql_clause(self, lat_col: str = "latitude", lng_col: str = "longitude") -> str:
        return f"{lat_col} BETWEEN ? AND ? AND {lng_col} BETWEEN ? AND ?"

    def to_sql_where(self, lat_col: str = "latitude", lng_col: str = "longitude") -> str:
        """Legacy embedded literals (prefer to_sql_clause + to_sql_params)."""
        return (
            f"{lat_col} BETWEEN {self.min_lat} AND {self.max_lat} "
            f"AND {lng_col} BETWEEN {self.min_lng} AND {self.max_lng}"
        )

class SpatialGridIndex:
    """
    In-memory spatial index (uniform grid).

    Insert points once, then query by bbox or radius (bbox cells → Haversine refine).
    Cell size is in degrees approx. from meters at reference latitude.
    """

    def __init__(self, cell_size_meters: float = 150.0, reference_lat: float = 52.0):
        self.cell_size_meters = max(25.0, float(cell_size_meters))
        self.reference_lat = float(reference_lat)
        lat_deg = (self.cell_size_meters / EARTH_RADIUS_METERS) * (180.0 / math.pi)
        cos_lat = max(0.05, abs(math.cos(math.radians(self.reference_lat))))
        lng_deg = (self.cell_size_meters / EARTH_RADIUS_METERS) * (180.0 / math.pi) / cos_lat
        self._lat_cell = max(1e-6, lat_deg)
        self._lng_cell = max(1e-6, lng_deg)
        self._cells: dict[tuple[int, int], list[dict[str, Any]]] = {}
        self._count = 0

    def clear(self) -> None:
        self._cells.clear()
        self._count = 0

    def _key(self, lat: float, lng: float) -> tuple[int, int]:
        return (int(math.floor(lat / self._lat_cell)), int(math.floor(lng / self._lng_cell)))

    def insert(self, lat: float, lng: float, payload: dict[str, Any]) -> None:
        key = self._key(lat, lng)
        item = {**payload, "lat": float(lat), "lng": float(lng)}
        self._cells.setdefault(key, []).append(item)
        self._count += 1

    def build(self, points: Iterable[dict[str, Any]], *, lat_key: str = "lat", lng_key: str = "lng") -> int:
        self.clear()
        n = 0
        for p in points or []:
            try:
                lat = float(p.get(lat_key))
                lng = float(p.get(lng_key))
            except (TypeError, ValueError):
                continue
            self.insert(lat, lng, dict(p))
            n += 1
        return n

    @property
    def size(self) -> int:
        return self._count

    def query_bbox(self, bbox: BoundingBox) -> list[dict[str, Any]]:
        i0, i1 = self._key(bbox.min_lat, bbox.min_lng)[0], self._key(bbox.max_lat, bbox.max_lng)[0]
        j0, j1 = self._key(bbox.min_lat, bbox.min_lng)[1], self._key(bbox.max_lat, bbox.max_lng)[1]
        if i0 > i1:
            i0, i1 = i1, i0
        if j0 > j1:
            j0, j1 = j1, j0
        out: list[dict[str, Any]] = []
        seen: set[int] = set()
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                for item in self._cells.get((i, j), []):
                    oid = id(item)
                    if oid in seen:
                        continue
                    if bbox.contains_lat_lng(float(item["lat"]), float(item["lng"])):
                        seen.add(oid)
                        out.append(item)
        return out

    def query_radius(
        self,
        lat: float,
        lng: float,
        radius_meters: float,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        bbox = BoundingBox.around_point(lat, lng, radius_meters)
        candidates = self.query_bbox(bbox)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for item in candidates:
            dist = haversine_meters(lat, lng, float(item["lat"]), float(item["lng"]))
            if dist <= radius_meters:
                ranked.append((dist, {**item, "distanceMeters": int(round(dist))}))
        ranked.sort(key=lambda t: (t[0], str(t[1].get("id") or "")))
        if limit is not None:
            ranked = ranked[: max(1, int(limit))]
        return [t[1] for t in ranked]


@dataclass
class GeospatialSearchResult:
    points: list[dict[str, Any]]
    total_considered: int = 0
    bbox_filtered: int = 0
    haversine_computed: int = 0
    cache_hit: bool = False
    elapsed_ms: float = 0.0
    method: str = "bbox+haversine"

    def to_meta(self) -> dict[str, Any]:
        return {
            "totalConsidered": self.total_considered,
            "bboxFiltered": self.bbox_filtered,
            "haversineComputed": self.haversine_computed,
            "cacheHit": self.cache_hit,
            "elapsedMs": round(self.elapsed_ms, 3),
            "method": self.method,
        }


class GeospatialOptimizer:
    """Bounding-box prune → Haversine refine, with optional grid index + LRU cache."""

    def __init__(self, cache_size: int = 1000, cache_ttl_seconds: int = 300):
        self.cache_size = max(100, cache_size)
        self.cache_ttl_seconds = max(10, cache_ttl_seconds)
        self._cache: dict[str, tuple[float, GeospatialSearchResult]] = {}
        self._cache_lock = threading.RLock()
        self._metrics = {
            "total_queries": 0,
            "cache_hits": 0,
            "total_haversine_calls": 0,
            "total_bbox_filters": 0,
            "grid_queries": 0,
        }
        self._metrics_lock = threading.RLock()

    def _cache_key(
        self,
        center_lat: float,
        center_lng: float,
        radius_meters: float,
        limit: int,
        query_id: str = "",
    ) -> str:
        return f"{round(center_lat, 4)}|{round(center_lng, 4)}|{int(radius_meters)}|{limit}|{query_id}"

    def _cache_get(self, key: str) -> GeospatialSearchResult | None:
        with self._cache_lock:
            hit = self._cache.get(key)
            if not hit:
                return None
            stored_at, result = hit
            if time.time() - stored_at > self.cache_ttl_seconds:
                del self._cache[key]
                return None
            self._record_metric("cache_hits")
            result.cache_hit = True
            return result

    def _cache_put(self, key: str, result: GeospatialSearchResult) -> None:
        with self._cache_lock:
            if len(self._cache) >= self.cache_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
            self._cache[key] = (time.time(), result)

    def _record_metric(self, metric_name: str, value: int = 1) -> None:
        with self._metrics_lock:
            if metric_name in self._metrics:
                self._metrics[metric_name] += value

    def find_nearest(
        self,
        center: GeoPoint,
        candidates: list[dict[str, Any]],
        *,
        limit: int = 5,
        radius_meters: float = 5000.0,
        filter_fn: Callable[[dict], bool] | None = None,
        cache_key: str = "",
        use_grid: bool = True,
        lat_key: str = "lat",
        lng_key: str = "lng",
    ) -> GeospatialSearchResult:
        start = time.time()
        self._record_metric("total_queries")

        if cache_key:
            cached = self._cache_get(cache_key)
            if cached:
                cached.elapsed_ms = (time.time() - start) * 1000
                return cached

        radius_meters = max(1.0, float(radius_meters))
        total = len(candidates or [])
        method = "bbox+haversine"

        if use_grid and total >= 40:
            grid = SpatialGridIndex(cell_size_meters=max(50.0, radius_meters / 8.0), reference_lat=center.lat)
            built = []
            for cand in candidates or []:
                if filter_fn is not None and not filter_fn(cand):
                    continue
                built.append(cand)
            grid.build(built, lat_key=lat_key, lng_key=lng_key)
            self._record_metric("grid_queries")
            method = "grid+bbox+haversine"
            radius_hits = grid.query_radius(center.lat, center.lng, radius_meters)
            self._record_metric("total_bbox_filters", total)
            self._record_metric("total_haversine_calls", len(radius_hits))
            ranked = sorted(
                radius_hits,
                key=lambda r: (int(r.get("distanceMeters") or 0), str(r.get("id") or "")),
            )
            bbox_n = len(radius_hits)
            hav_n = len(radius_hits)
        else:
            bbox = BoundingBox.around_point(center.lat, center.lng, radius_meters)
            bbox_filtered: list[dict[str, Any]] = []
            for cand in candidates or []:
                try:
                    clat = float(cand.get(lat_key))
                    clng = float(cand.get(lng_key))
                except (TypeError, ValueError):
                    continue
                if not bbox.contains_lat_lng(clat, clng):
                    continue
                if filter_fn is not None and not filter_fn(cand):
                    continue
                bbox_filtered.append(cand)

            self._record_metric("total_bbox_filters", total)
            ranked_pairs: list[tuple[float, dict[str, Any]]] = []
            for cand in bbox_filtered:
                try:
                    clat = float(cand.get(lat_key))
                    clng = float(cand.get(lng_key))
                    dist = haversine_meters(center.lat, center.lng, clat, clng)
                except (TypeError, ValueError):
                    continue
                if dist <= radius_meters:
                    ranked_pairs.append((dist, cand))
            self._record_metric("total_haversine_calls", len(bbox_filtered))
            ranked_pairs.sort(key=lambda t: (t[0], str(t[1].get("id") or "")))
            ranked = [
                {
                    **cand,
                    "lat": float(cand.get(lat_key)),
                    "lng": float(cand.get(lng_key)),
                    "distanceMeters": int(round(dist)),
                }
                for dist, cand in ranked_pairs
            ]
            bbox_n = len(bbox_filtered)
            hav_n = len(bbox_filtered)

        top_n = max(1, min(int(limit or 5), 100))
        results = ranked[:top_n]
        elapsed = (time.time() - start) * 1000
        result = GeospatialSearchResult(
            points=results,
            total_considered=total,
            bbox_filtered=bbox_n,
            haversine_computed=hav_n,
            cache_hit=False,
            elapsed_ms=elapsed,
            method=method,
        )
        if cache_key:
            self._cache_put(cache_key, result)
        return result

    def find_nearest_in_db(
        self,
        db,
        center: GeoPoint,
        *,
        table: str,
        lat_col: str = "latitude",
        lng_col: str = "longitude",
        limit: int = 5,
        radius_meters: float = 5000.0,
        extra_where: str = "",
        extra_params: tuple[Any, ...] | list[Any] | None = None,
        where_clause: str = "",
        where_params: dict[str, Any] | tuple[Any, ...] | list[Any] | None = None,
        cache_key: str = "",
    ) -> GeospatialSearchResult:
        """DB-level bbox (BETWEEN) then Haversine — SQLite-safe parameterized query."""
        start = time.time()
        self._record_metric("total_queries")
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached:
                cached.elapsed_ms = (time.time() - start) * 1000
                return cached

        radius_meters = max(1.0, float(radius_meters))
        bbox = BoundingBox.around_point(center.lat, center.lng, radius_meters)
        clause = bbox.to_sql_clause(lat_col, lng_col)
        params: list[Any] = list(bbox.to_sql_params())
        where = clause

        # Prefer new extra_* API; keep where_clause/where_params for callers.
        extra = str(extra_where or where_clause or "").strip()
        if extra:
            where = f"({clause}) AND ({extra})"
            if extra_params is not None:
                params.extend(list(extra_params))
            elif isinstance(where_params, dict):
                # Named placeholders were never used; append values in clause "?" order.
                # Common pattern: "company_id = ?" with {"company_id": id}
                for _key, val in where_params.items():
                    params.append(val)
            elif where_params is not None:
                params.extend(list(where_params))

        # Whitelist table/column names — callers must pass trusted identifiers.
        sql = f"SELECT * FROM {table} WHERE {where}"
        try:
            rows = db.execute(sql, tuple(params)).fetchall()
        except Exception:
            rows = []

        self._record_metric("total_bbox_filters", len(rows) if rows else 0)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for row in rows or []:
            try:
                item = dict(row)
                clat = float(item.get(lat_col))
                clng = float(item.get(lng_col))
                dist = haversine_meters(center.lat, center.lng, clat, clng)
            except (TypeError, ValueError):
                continue
            if dist <= radius_meters:
                ranked.append((dist, item))
        self._record_metric("total_haversine_calls", len(rows) if rows else 0)
        ranked.sort(key=lambda t: t[0])
        top_n = max(1, min(int(limit or 5), 100))
        results = [
            {
                "id": str(item.get("id", "")),
                "name": str(item.get("name") or item.get("site_name") or ""),
                "lat": float(item.get(lat_col)),
                "lng": float(item.get(lng_col)),
                "distanceMeters": int(round(dist)),
                **{
                    k: v
                    for k, v in item.items()
                    if k not in {"id", "name", "site_name", lat_col, lng_col}
                },
            }
            for dist, item in ranked[:top_n]
        ]
        elapsed = (time.time() - start) * 1000
        result = GeospatialSearchResult(
            points=results,
            total_considered=len(rows) if rows else 0,
            bbox_filtered=len(rows) if rows else 0,
            haversine_computed=len(rows) if rows else 0,
            elapsed_ms=elapsed,
            method="sql-bbox+haversine",
        )
        if cache_key:
            self._cache_put(cache_key, result)
        return result
    def get_metrics(self) -> dict[str, Any]:
        with self._metrics_lock:
            return {
                **self._metrics,
                "cache_size": len(self._cache),
                "cache_hit_rate": self._metrics["cache_hits"] / max(1, self._metrics["total_queries"]),
            }

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def reset_metrics(self) -> None:
        with self._metrics_lock:
            for key in list(self._metrics.keys()):
                self._metrics[key] = 0


_optimizer: GeospatialOptimizer | None = None
_optimizer_lock = threading.Lock()


def get_optimizer(cache_size: int = 1000, cache_ttl_seconds: int = 120) -> GeospatialOptimizer:
    global _optimizer
    if _optimizer is None:
        with _optimizer_lock:
            if _optimizer is None:
                _optimizer = GeospatialOptimizer(cache_size, cache_ttl_seconds)
    return _optimizer


def point_in_circle_bbox_then_haversine(
    lat: float,
    lng: float,
    center_lat: float,
    center_lng: float,
    radius_meters: float,
) -> tuple[bool, float | None]:
    """Fast containment: bbox reject, then Haversine. Returns (inside, distance_m|None)."""
    bbox = BoundingBox.from_circle(center_lat, center_lng, radius_meters)
    if not bbox.contains_lat_lng(lat, lng):
        return False, None
    dist = haversine_meters(lat, lng, center_lat, center_lng)
    return dist <= radius_meters, dist
