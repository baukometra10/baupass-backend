"""Transfer archive schema (2026-08-transfer-v1)."""
from __future__ import annotations

SCHEMA_VERSION = "2026-08-transfer-v1"
LEGACY_SCHEMA_PREFIX = "2026-04-export-v2"

# Phase A domains — order matters for apply (parents before children).
PHASE_A_DOMAINS: tuple[str, ...] = (
    "companies",
    "subcompanies",
    "workers",
    "contract_templates",
    "employment_contracts",
    "worker_documents",
    "access_logs",
    "invoices",
    "deployment_days",
    "leave_requests",
)

DOMAIN_WEIGHTS: dict[str, float] = {
    "companies": 8,
    "subcompanies": 4,
    "workers": 22,
    "contract_templates": 4,
    "employment_contracts": 16,
    "worker_documents": 16,
    "access_logs": 10,
    "invoices": 8,
    "deployment_days": 8,
    "leave_requests": 4,
}
