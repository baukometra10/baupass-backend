"""Generic tabular PDF reports (invoices, companies, exports)."""
from __future__ import annotations

from typing import Any, Sequence

from backend.app.platform.reports.report_pdf_layout import build_branded_table_report_pdf


def build_table_report_pdf(
    *,
    title: str,
    subtitle: str = "",
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    landscape_mode: bool = False,
    branding: dict[str, Any] | None = None,
) -> bytes:
    return build_branded_table_report_pdf(
        report_title=title,
        subtitle=subtitle,
        branding=branding or {},
        headers=headers,
        rows=rows,
        landscape_mode=landscape_mode,
    )
