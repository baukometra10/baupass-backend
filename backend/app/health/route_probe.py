"""API route registration probes for health checks and deploy gates."""
from __future__ import annotations

from typing import Any, Callable

CRITICAL_API_ROUTES: tuple[tuple[str, frozenset[str]], ...] = (
    ("/api/companies", frozenset({"GET", "POST"})),
    ("/api/companies/<company_id>", frozenset({"PUT"})),
    ("/api/companies/<company_id>/mail-settings", frozenset({"GET"})),
    ("/api/companies/<company_id>/admin-security", frozenset({"GET"})),
    ("/api/companies/<company_id>/turnstiles", frozenset({"GET"})),
    ("/api/settings", frozenset({"GET", "PUT"})),
    ("/api/ops/guidance", frozenset({"GET"})),
    ("/api/workforce/deployment-plan/pdf/branding-preview", frozenset({"POST"})),
    ("/api/v2/billing/pricing", frozenset({"GET"})),
    ("/api/ops-os/events/stream", frozenset({"GET"})),
)


def _probe_key(path: str) -> str:
    return (
        path.replace("/api/", "")
        .replace("<company_id>", "company")
        .replace("/", "_")
        .strip("_")
    )


def build_api_route_probe(route_methods_for: Callable[[str], set[str]]) -> dict[str, Any]:
    routes: dict[str, bool] = {}
    missing: list[dict[str, Any]] = []
    for path, required in CRITICAL_API_ROUTES:
        available = route_methods_for(path)
        route_ok = required.issubset(available)
        routes[_probe_key(path)] = route_ok
        if not route_ok:
            missing.append(
                {
                    "path": path,
                    "required": sorted(required),
                    "available": sorted(available),
                }
            )
    return {"ok": not missing, "routes": routes, "missing": missing}


def summarize_blueprint_status(app) -> dict[str, Any]:
    modular = app.extensions.get("modular_blueprints") or []
    domains = app.extensions.get("domain_blueprints") or []
    retries = app.extensions.get("domain_blueprint_retries") or []

    def _failed(entries: list) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for entry in entries:
            if isinstance(entry, dict):
                status = str(entry.get("status") or "")
                if status != "ok":
                    out.append(
                        {
                            "name": entry.get("name"),
                            "status": status,
                            "error": entry.get("error"),
                            "category": entry.get("category"),
                        }
                    )
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2 and entry[1] != "ok":
                out.append({"name": entry[0], "status": entry[1]})
        return out

    failed_modular = _failed(modular if isinstance(modular, list) else [])
    failed_domains = _failed(domains if isinstance(domains, list) else [])
    failed_retries = _failed(retries if isinstance(retries, list) else [])

    return {
        "modularBlueprints": modular,
        "domainBlueprints": domains,
        "domainBlueprintRetries": retries,
        "failedModular": failed_modular,
        "failedDomains": failed_domains,
        "failedRetries": failed_retries,
        "healthy": not (failed_modular or failed_domains),
    }
