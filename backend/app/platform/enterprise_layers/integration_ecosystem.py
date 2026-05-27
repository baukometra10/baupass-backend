"""
Enterprise Integration Ecosystem — provider catalog + connection status.
"""
from __future__ import annotations

from typing import Any


PROVIDER_CATALOG = (
    {"id": "microsoft365", "category": "productivity", "auth": "oauth"},
    {"id": "google_workspace", "category": "productivity", "auth": "oauth"},
    {"id": "payroll", "category": "payroll", "auth": "config"},
    {"id": "sap", "category": "erp", "auth": "token"},
    {"id": "oracle", "category": "erp", "auth": "token"},
    {"id": "stripe", "category": "billing", "auth": "api_key"},
    {"id": "gate_devices", "category": "access", "auth": "gate_key", "api": "/api/gates/tap"},
    {"id": "turnstile_ingest", "category": "access", "auth": "device_key", "api": "/api/device/ingest"},
    {"id": "iot_telemetry", "category": "iot", "auth": "device", "api": "/api/iot/devices/{id}/telemetry"},
    {"id": "security_cameras", "category": "security", "auth": "webhook", "api": "/api/integrations/security-cameras/events"},
    {"id": "biometric_readers", "category": "access", "auth": "webhook", "api": "/api/integrations/biometric/events"},
)


def build_integration_ecosystem(db, company_id: int) -> dict[str, Any]:
    rows = db.execute(
        "SELECT provider, status, updated_at FROM integration_connections WHERE company_id = ?",
        (company_id,),
    ).fetchall()
    connected = {str(r["provider"]): dict(r) for r in rows}
    providers = []
    for item in PROVIDER_CATALOG:
        pid = item["id"]
        conn = connected.get(pid)
        providers.append(
            {
                **item,
                "connected": bool(conn),
                "connection_status": (conn or {}).get("status"),
                "updated_at": (conn or {}).get("updated_at"),
            }
        )
    return {
        "layer": "enterprise_integration_ecosystem",
        "status": "active",
        "company_id": company_id,
        "providers": providers,
        "connect_api": "/api/integrations/{provider}/connect",
        "sync_api": "/api/integrations/{provider}/sync",
    }
