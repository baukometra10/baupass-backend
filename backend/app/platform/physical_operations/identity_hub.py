"""Enterprise Digital Identity Platform — unified identity surface."""
from __future__ import annotations

from typing import Any


def build_identity_hub(db, company_id: int, worker_id: str | None = None) -> dict[str, Any]:
    if worker_id:
        w = db.execute(
            """
            SELECT id, first_name, last_name, badge_id, status, company_id,
                   physical_card_id, worker_type
            FROM workers WHERE id = ? AND company_id = ?
            """,
            (worker_id, company_id),
        ).fetchone()
        if not w:
            return {"error": "worker_not_found"}
        passes = db.execute(
            "SELECT pass_type, platform, status FROM worker_passes WHERE worker_id = ?",
            (worker_id,),
        ).fetchall()
        perms = db.execute(
            "SELECT zone_id, allowed_from, allowed_until FROM access_permissions WHERE company_id = ? AND worker_id = ?",
            (company_id, worker_id),
        ).fetchall()
        return {
            "layer": "enterprise_digital_identity",
            "worker": dict(w),
            "channels": {
                "qr": True,
                "badge_pin": bool(w["badge_id"]),
                "nfc": bool(str(w["physical_card_id"] or "").strip()),
                "hce": True,
                "wallet": [{"type": p["pass_type"], "platform": p["platform"], "status": p["status"]} for p in passes],
            },
            "accessPermissions": [dict(p) for p in perms],
            "rbacNote": "Company roles via /api/roles; worker access via gates and permissions",
        }
    summary = db.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN TRIM(COALESCE(badge_id,'')) != '' THEN 1 ELSE 0 END) AS with_badge,
            SUM(CASE WHEN status = 'aktiv' THEN 1 ELSE 0 END) AS active
        FROM workers WHERE company_id = ? AND deleted_at IS NULL
        """,
        (company_id,),
    ).fetchone()
    wallet_count = db.execute(
        """
        SELECT COUNT(*) AS c FROM worker_passes wp
        JOIN workers w ON w.id = wp.worker_id
        WHERE w.company_id = ? AND wp.status = 'active'
        """,
        (company_id,),
    ).fetchone()
    return {
        "layer": "enterprise_digital_identity",
        "companyId": company_id,
        "summary": {
            "workers": int((summary["total"] if summary else 0) or 0),
            "withBadge": int((summary["with_badge"] if summary else 0) or 0),
            "active": int((summary["active"] if summary else 0) or 0),
            "activeWalletPasses": int((wallet_count["c"] if wallet_count else 0) or 0),
        },
        "unifiedChannels": ["qr", "badge_pin", "nfc", "hce", "wallet", "rbac", "geofence"],
        "apis": {
            "worker_app": "/api/worker-app/*",
            "gates": "/api/gates/tap",
            "scan": "/api/scan",
            "permissions": "/api/access-permissions",
            "roles": "/api/roles",
            "mobile_distribution": "/api/v2/mobile/distribution",
        },
    }
