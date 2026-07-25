"""Nearest police suggestion — assisted escalation only (no auto-dial)."""
from __future__ import annotations

import math
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


def suggest_nearest_police(
    *,
    country: str = "",
    city: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    """Return a suggestion pack for human-assisted escalation (never auto-calls)."""
    cc = normalize_country(country)
    city_l = str(city or "").strip().lower()
    emergency = _COUNTRY_EMERGENCY.get(cc) or {"emergency": "112", "label": "Police / emergency"}

    candidates = list(_STATIONS)
    if cc:
        same_country = [s for s in candidates if s["country"] == cc]
        if same_country:
            candidates = same_country
    if city_l:
        city_match = [s for s in candidates if city_l in str(s.get("city") or "").lower()]
        if city_match:
            candidates = city_match

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

    if best:
        return {
            "ok": True,
            "autoDial": False,
            "disclaimer": (
                "Assisted suggestion only. Do not treat AI camera alerts as confirmed theft. "
                "A human must decide whether to contact police."
            ),
            "station": {
                "name": best["name"],
                "address": best["address"],
                "phone": best["phone"],
                "country": best["country"],
                "city": best["city"],
                "distanceKm": round(best_km, 1) if best_km is not None else None,
            },
            "countryEmergency": {
                "number": emergency["emergency"],
                "label": emergency["label"],
                "country": cc or best["country"],
            },
            "action": "human_confirm",
        }

    return {
        "ok": True,
        "autoDial": False,
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
