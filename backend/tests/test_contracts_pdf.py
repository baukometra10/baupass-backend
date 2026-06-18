from backend.app.domains.contracts.contract_locales import (
    build_fallback_contract_body,
    default_currency_for_jurisdiction,
    default_lang_for_jurisdiction,
    document_title,
    jurisdiction_name,
    normalize_jurisdiction,
)
from backend.app.platform.reports.contracts_pdf import build_employment_contract_pdf


def test_build_employment_contract_pdf_de_germany():
    pdf_bytes = build_employment_contract_pdf(
        contract={
            "title": "Arbeitsvertrag",
            "language": "de",
            "final_text": "",
            "input_data": {
                "form": {
                    "jurisdiction": "DE",
                    "employee_name": "Max Mustermann",
                    "employee_address": "Musterstraße 1, 10115 Berlin",
                    "job_title": "Bürokraft",
                    "start_date": "01.07.2026",
                    "weekly_hours": "40",
                    "vacation_days": "30",
                    "probation_months": "6",
                    "salary_type": "monthly_fixed",
                    "salary_gross_monthly": "3200",
                    "currency": "EUR",
                },
                "company": {"name": "Muster GmbH"},
            },
        },
        branding={"companyName": "Muster GmbH"},
    )
    assert pdf_bytes.startswith(b"%PDF")
    body = build_fallback_contract_body(
        lang="de",
        jurisdiction="DE",
        form={"jurisdiction": "DE"},
        notes="",
    )
    assert "§ 1 Beginn" in body
    assert document_title("de", "DE") == "Arbeitsvertrag (ohne Tarifbindung)"


def test_build_employment_contract_pdf_en_uae():
    pdf_bytes = build_employment_contract_pdf(
        contract={
            "language": "en",
            "final_text": "",
            "input_data": {
                "form": {
                    "jurisdiction": "AE",
                    "employee_name": "Jane Doe",
                    "employee_address": "Dubai",
                    "job_title": "Sales Associate",
                    "start_date": "2026-07-01",
                    "salary_type": "monthly_fixed",
                    "salary_gross_monthly": "12000",
                    "currency": "AED",
                },
                "company": {"name": "Example LLC"},
            },
        },
        branding={"companyName": "Example LLC"},
    )
    assert pdf_bytes.startswith(b"%PDF")
    body = build_fallback_contract_body(
        lang="en",
        jurisdiction="AE",
        form={"jurisdiction": "AE", "job_title": "Sales Associate"},
        notes="",
    )
    assert "Section 1" in body
    assert "UAE" in body or "Emirates" in body


def test_build_employment_contract_pdf_ar_saudi():
    pdf_bytes = build_employment_contract_pdf(
        contract={
            "language": "ar",
            "final_text": "",
            "input_data": {
                "form": {
                    "jurisdiction": "SA",
                    "employee_name": "أحمد",
                    "employee_address": "الرياض",
                    "job_title": "محاسب",
                    "start_date": "2026-07-01",
                    "salary_type": "monthly_fixed",
                    "salary_gross_monthly": "9000",
                    "currency": "SAR",
                },
                "company": {"name": "شركة مثال"},
            },
        },
        branding={"companyName": "شركة مثال"},
    )
    assert pdf_bytes.startswith(b"%PDF")
    body = build_fallback_contract_body(
        lang="ar",
        jurisdiction="SA",
        form={"jurisdiction": "SA", "job_title": "محاسب"},
        notes="",
    )
    assert "المادة 1" in body


def test_jurisdiction_defaults():
    assert default_currency_for_jurisdiction("AE") == "AED"
    assert default_lang_for_jurisdiction("SA") == "ar"
    assert jurisdiction_name("US", "de") == "USA"
    assert normalize_jurisdiction("XX") == "INT"
