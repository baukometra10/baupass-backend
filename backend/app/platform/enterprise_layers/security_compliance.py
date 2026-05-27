"""
Enterprise Security & Compliance Layer snapshot.
"""
from __future__ import annotations

import os
from typing import Any


COMPLIANCE_STANDARDS = (
    {"id": "gdpr", "name": "GDPR", "features": ["data_export", "erasure_requests", "audit_logs"]},
    {"id": "immutable_audit", "name": "Immutable audit", "env": "BAUPASS_IMMUTABLE_AUDIT"},
    {"id": "rbac", "name": "Advanced RBAC", "endpoints": ["/api/roles"]},
    {"id": "session_devices", "name": "Session device binding", "env": "BAUPASS_ZERO_TRUST_DEVICE_BINDING"},
    {"id": "field_encryption", "name": "Field encryption", "env": "BAUPASS_FIELD_ENCRYPTION_KEY"},
)


def build_security_compliance_layer(db) -> dict[str, Any]:
    failed_logins = 0
    try:
        row = db.execute(
            """
            SELECT COUNT(*) AS c FROM audit_logs
            WHERE event_type LIKE '%login.failed%'
              AND created_at >= datetime('now', '-24 hours')
            """
        ).fetchone()
        failed_logins = int((row["c"] if row else 0) or 0)
    except Exception:
        pass

    standards = []
    for std in COMPLIANCE_STANDARDS:
        env_key = std.get("env")
        enabled = bool(os.getenv(env_key, "").strip()) if env_key else True
        standards.append({**std, "enabled": enabled})

    return {
        "layer": "enterprise_security_compliance",
        "status": "active",
        "zero_trust": {
            "enabled": os.getenv("BAUPASS_ZERO_TRUST", "0") in {"1", "true", "yes"},
            "device_binding": os.getenv("BAUPASS_ZERO_TRUST_DEVICE_BINDING", "0") in {"1", "true", "yes"},
        },
        "encryption": bool(os.getenv("BAUPASS_FIELD_ENCRYPTION_KEY", "").strip()),
        "immutable_audit": os.getenv("BAUPASS_IMMUTABLE_AUDIT", "0") in {"1", "true", "yes"},
        "siem": {
            "export": "/api/enterprise/security/siem-export",
            "log_forwarder": bool(os.getenv("BAUPASS_LOG_FORWARD_URL", "").strip()),
        },
        "threat_monitoring": {
            "failed_logins_24h": failed_logins,
            "alert_threshold": 50,
            "elevated": failed_logins >= 50,
        },
        "compliance_standards": standards,
        "rbac": True,
        "session_security": True,
    }
