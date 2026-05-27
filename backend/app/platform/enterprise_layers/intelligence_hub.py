"""
Enterprise Intelligence Layer — unified analytics bundle.
"""
from __future__ import annotations

from typing import Any


def build_intelligence_layer(db, company_id: int) -> dict[str, Any]:
    cid = str(company_id)
    from backend.app.platform.ai.intelligence import operational_insights
    from backend.app.platform.ai.behavior_patterns import analyze_behavior_patterns
    from backend.app.platform.operations.intelligence import (
        ai_scheduling_hints,
        predictive_workforce_plan,
        resource_allocation,
        workforce_optimization,
    )

    return {
        "layer": "enterprise_intelligence",
        "status": "active",
        "company_id": company_id,
        "modules": {
            "operational_insights": operational_insights(db, cid),
            "behavior_patterns": analyze_behavior_patterns(db, company_id, days=14),
            "workforce_optimization": workforce_optimization(db, company_id),
            "resource_allocation": resource_allocation(db, company_id),
            "scheduling_hints": ai_scheduling_hints(db, company_id),
            "workforce_forecast": predictive_workforce_plan(db, company_id, horizon_days=14),
        },
        "capabilities": [
            "behavior_analysis",
            "predictive_attendance",
            "fraud_detection",
            "productivity_analytics",
            "workforce_risk",
            "workforce_optimization",
            "smart_scheduling",
        ],
    }
