"""Nearest police suggestion — assisted escalation only (no auto-dial)."""
from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

# Curated sample stations + country emergency numbers for worldwide fallback.
_COUNTRY_EMERGENCY = {
    "DE": {"emergency": "110", "label": "Polizei"},
    "AT": {"emergency": "133", "label": "Polizei"},
    "CH": {"emergency": "117", "label": "Polizei"},
    "FR": {"emergency": "17", "label": "Police"},
    "BE": {"emergency": "101", "label": "Police"},
    "NL": {"emergency": "112", "label": "Politie"},
    "PL": {"emergency": "997", "label": "Policja"},
    "IT": {"emergency": "112", "label": "Polizia"},
    "ES": {"emergency": "091", "label": "Policía"},
    "GB": {"emergency": "999", "label": "Police"},
    "UK": {"emergency": "999", "label": "Police"},
    "US": {"emergency": "911", "label": "Police"},
    "CA": {"emergency": "911", "label": "Police"},
    "AU": {"emergency": "000", "label": "Police"},
    "AE": {"emergency": "999", "label": "Police"},
    "SA": {"emergency": "999", "label": "Police"},
    "TR": {"emergency": "155", "label": "Polis"},
    "EG": {"emergency": "122", "label": "Police"},
    "SE": {"emergency": "112", "label": "Polis"},
    "NO": {"emergency": "112", "label": "Politi"},
    "DK": {"emergency": "114", "label": "Politi"},
    "FI": {"emergency": "112", "label": "Poliisi"},
    "PT": {"emergency": "112", "label": "Polícia"},
    "IE": {"emergency": "999", "label": "Garda"},
    "IN": {"emergency": "112", "label": "Police"},
    "BR": {"emergency": "190", "label": "Polícia"},
    "MX": {"emergency": "911", "label": "Policía"},
    "JP": {"emergency": "110", "label": "Police"},
    "KR": {"emergency": "112", "label": "Police"},
    "CN": {"emergency": "110", "label": "Police"},
    "ZA": {"emergency": "10111", "label": "Police"},
}

_STATIONS: list[dict[str, Any]] = [
    {
        "name": "Polizeidirektion Berlin Mitte",
        "address": "Keibelstraße 36, 10178 Berlin",
        "phone": "+49 30 46640",
        "country": "DE",
        "city": "Berlin",
        "lat": 52.525,
        "lng": 13.415,
    },
    {
        "name": "Polizeipräsidium München",
        "address": "Ettstraße 2, 80333 München",
        "phone": "+49 89 29100",
        "country": "DE",
        "city": "München",
        "lat": 48.139,
        "lng": 11.566,
    },
    {
        "name": "Polizeipräsidium Hamburg",
        "address": "Bruno-Georges-Platz 1, 22297 Hamburg",
        "phone": "+49 40 42860",
        "country": "DE",
        "city": "Hamburg",
        "lat": 53.605,
        "lng": 10.021,
    },
    {
        "name": "Polizeipräsidium Köln",
        "address": "Walter-Pauli-Ring 2-4, 51103 Köln",
        "phone": "+49 221 2290",
        "country": "DE",
        "city": "Köln",
        "lat": 50.937,
        "lng": 6.960,
    },
    {
        "name": "Polizeipräsidium Frankfurt",
        "address": "Adickesallee 70, 60322 Frankfurt",
        "phone": "+49 69 7550",
        "country": "DE",
        "city": "Frankfurt",
        "lat": 50.134,
        "lng": 8.681,
    },
    {
        "name": "Polizeiinspektion Wien Innenstadt",
        "address": "Deutschmeisterplatz 3, 1010 Wien",
        "phone": "+43 1 31310",
        "country": "AT",
        "city": "Wien",
        "lat": 48.216,
        "lng": 16.372,
    },
    {
        "name": "Police Prefecture of Paris",
        "address": "1 Rue de Lutèce, 75004 Paris",
        "phone": "+33 1 53 71 53 71",
        "country": "FR",
        "city": "Paris",
        "lat": 48.856,
        "lng": 2.348,
    },
    {
        "name": "Metropolitan Police — New Scotland Yard",
        "address": "Victoria Embankment, London SW1A 2JL",
        "phone": "+44 101",
        "country": "GB",
        "city": "London",
        "lat": 51.502,
        "lng": -0.124,
    },
    {
        "name": "NYPD Midtown South Precinct",
        "address": "357 W 35th St, New York, NY 10001",
        "phone": "+1 212-239-9811",
        "country": "US",
        "city": "New York",
        "lat": 40.754,
        "lng": -73.994,
    },
    {
        "name": "Dubai Police HQ",
        "address": "Al Wasl Rd, Dubai",
        "phone": "+971 4 609 9999",
        "country": "AE",
        "city": "Dubai",
        "lat": 25.204,
        "lng": 55.271,
    },
    {
        "name": "Istanbul Emniyet Müdürlüğü",
        "address": "Vatan Cad., Fatih, Istanbul",
        "phone": "+90 212 455 9000",
        "country": "TR",
        "city": "Istanbul",
        "lat": 41.018,
        "lng": 28.940,
    },
    {
        "name": "Cairo Security Directorate",
        "address": "Cairo, Egypt",
        "phone": "122",
        "country": "EG",
        "city": "Cairo",
        "lat": 30.044,
        "lng": 31.236,
    },
]


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def normalize_country(code: str) -> str:
    c = str(code or "").strip().upper()
    aliases = {"DEU": "DE", "GER": "DE", "AUT": "AT", "CHE": "CH", "FRA": "FR", "USA": "US", "GBR": "GB"}
    return aliases.get(c, c[:2] if len(c) >= 2 else c)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _cache_get(db, cache_key: str) -> dict[str, Any] | None:
    if db is None:
        return None
    try:
        row = db.execute(
            "SELECT payload_json, expires_at FROM police_station_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    try:
        exp = str(row["expires_at"] or "").replace("Z", "+00:00")
        if datetime.fromisoformat(exp) < datetime.now(timezone.utc):
            return None
        return json.loads(row["payload_json"] or "{}")
    except Exception:
        return None


def _cache_put(db, cache_key: str, country: str, city: str, payload: dict[str, Any], *, hours: int = 168) -> None:
    if db is None:
        return
    try:
        expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        db.execute(
            """
            INSERT INTO police_station_cache (cache_key, country, city, payload_json, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload_json = excluded.payload_json,
                expires_at = excluded.expires_at,
                created_at = excluded.created_at
            """,
            (cache_key, country, city, json.dumps(payload, ensure_ascii=False), _now_iso(), expires),
        )
        db.commit()
    except Exception:
        pass


def _overpass_nearby(lat: float, lng: float, *, radius_m: int = 8000) -> list[dict[str, Any]]:
    if str(os.getenv("BAUPASS_POLICE_OSM", "1")).strip().lower() in {"0", "false", "off", "no"}:
        return []
    query = f"""
    [out:json][timeout:12];
    (
      node["amenity"="police"](around:{radius_m},{lat},{lng});
      way["amenity"="police"](around:{radius_m},{lat},{lng});
    );
    out center 8;
    """
    endpoints = [
        os.getenv("BAUPASS_OVERPASS_URL", "").strip(),
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    for url in endpoints:
        if not url:
            continue
        try:
            req = urllib.request.Request(url, data=data, method="POST", headers={"User-Agent": "WorkPassCameraWatch/1.0"})
            with urllib.request.urlopen(req, timeout=14) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            out: list[dict[str, Any]] = []
            for el in payload.get("elements") or []:
                tags = el.get("tags") or {}
                if el.get("type") == "node":
                    elat, elng = el.get("lat"), el.get("lon")
                else:
                    center = el.get("center") or {}
                    elat, elng = center.get("lat"), center.get("lon")
                if elat is None or elng is None:
                    continue
                out.append(
                    {
                        "name": tags.get("name") or tags.get("official_name") or "Police station",
                        "address": ", ".join(
                            x
                            for x in [
                                tags.get("addr:street"),
                                tags.get("addr:housenumber"),
                                tags.get("addr:postcode"),
                                tags.get("addr:city"),
                            ]
                            if x
                        )
                        or tags.get("addr:full")
                        or "",
                        "phone": tags.get("phone") or tags.get("contact:phone") or "",
                        "country": "",
                        "city": tags.get("addr:city") or "",
                        "lat": float(elat),
                        "lng": float(elng),
                        "source": "osm",
                    }
                )
            return out
        except Exception:
            continue
    return []


def _pick_best(candidates: list[dict[str, Any]], latitude: float | None, longitude: float | None):
    best = None
    best_km = None
    if latitude is not None and longitude is not None:
        for s in candidates:
            try:
                d = _haversine_km(float(latitude), float(longitude), float(s["lat"]), float(s["lng"]))
            except Exception:
                continue
            if best is None or d < (best_km or 1e18):
                best, best_km = s, d
    if best is None and candidates:
        best = candidates[0]
    return best, best_km


def suggest_nearest_police(
    *,
    country: str = "",
    city: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    db=None,
) -> dict[str, Any]:
    """Return a suggestion pack for human-assisted escalation (never auto-calls)."""
    cc = normalize_country(country)
    city_l = str(city or "").strip().lower()
    emergency = _COUNTRY_EMERGENCY.get(cc) or {"emergency": "112", "label": "Police / emergency"}
    cache_key = f"{cc}|{city_l}|{round(float(latitude), 3) if latitude is not None else ''}|{round(float(longitude), 3) if longitude is not None else ''}"

    cached = _cache_get(db, cache_key)
    if cached and cached.get("station"):
        cached["autoDial"] = False
        cached["fromCache"] = True
        return cached

    candidates = list(_STATIONS)
    if cc:
        same_country = [s for s in candidates if s["country"] == cc]
        if same_country:
            candidates = same_country
    if city_l:
        city_match = [s for s in candidates if city_l in str(s.get("city") or "").lower()]
        if city_match:
            candidates = city_match

    osm: list[dict[str, Any]] = []
    if latitude is not None and longitude is not None:
        osm = _overpass_nearby(float(latitude), float(longitude))
        for s in osm:
            s["country"] = s.get("country") or cc
        candidates = osm + candidates

    best, best_km = _pick_best(candidates, latitude, longitude)

    if best:
        result = {
            "ok": True,
            "autoDial": False,
            "fromCache": False,
            "source": best.get("source") or "directory",
            "disclaimer": (
                "Assisted suggestion only. Do not treat AI camera alerts as confirmed theft. "
                "A human must decide whether to contact police."
            ),
            "station": {
                "name": best["name"],
                "address": best.get("address") or "",
                "phone": best.get("phone") or emergency["emergency"],
                "country": best.get("country") or cc,
                "city": best.get("city") or city,
                "distanceKm": round(best_km, 1) if best_km is not None else None,
            },
            "countryEmergency": {
                "number": emergency["emergency"],
                "label": emergency["label"],
                "country": cc or best.get("country") or "",
            },
            "action": "human_confirm",
        }
        _cache_put(db, cache_key, cc, city, result)
        return result

    result = {
        "ok": True,
        "autoDial": False,
        "fromCache": False,
        "disclaimer": (
            "No station directory match. Use the local emergency number and locate the nearest station manually."
        ),
        "station": None,
        "countryEmergency": {
            "number": emergency["emergency"],
            "label": emergency["label"],
            "country": cc or "",
        },
        "action": "human_confirm",
    }
    _cache_put(db, cache_key, cc, city, result, hours=24)
    return result
