from backend.app.domains.contracts.validation import validate_contract_form
from backend.app.platform.notifications.sms import send_sms, sms_configured


def test_sms_not_configured_without_env(monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_FROM_NUMBER", raising=False)
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("SENDINBLUE_API_KEY", raising=False)
    monkeypatch.setattr(
        "backend.app.platform.notifications.sms._brevo_api_key",
        lambda: "",
    )
    assert sms_configured() is False
    ok, err = send_sms(to="+491234567890", body="test")
    assert not ok
    assert err == "sms_not_configured"


def test_brevo_sms_preferred_when_configured(monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("BREVO_SMS_SENDER", "SUPPIX")
    monkeypatch.setattr(
        "backend.app.platform.notifications.sms._send_via_brevo",
        lambda **kwargs: (True, ""),
    )
    assert sms_configured() is True
    ok, err = send_sms(to="+491701234567", body="Code 123456")
    assert ok is True
    assert err == ""


def test_validate_contract_form_requires_gender():
    missing = validate_contract_form(
        {
            "employee_name": "Max",
            "employee_address": "Berlin",
            "job_title": "Clerk",
            "start_date": "2026-01-01",
            "work_location": "Office",
            "salary_gross_monthly": "2000",
        },
        lang="de",
    )
    assert any("Anrede" in m or "gender" in m.lower() for m in missing)


def test_validate_contract_form_ok():
    missing = validate_contract_form(
        {
            "employee_name": "Max Mustermann",
            "employee_gender": "male",
            "employee_address": "Berlin",
            "job_title": "Clerk",
            "start_date": "2026-01-01",
            "work_location": "Office",
            "salary_gross_monthly": "2000",
        },
        lang="de",
    )
    assert missing == []


def test_validate_hourly_does_not_require_gross_monthly():
    template = {"contract_type": "employment", "required_fields_json": '["salary_gross_monthly"]'}
    missing = validate_contract_form(
        {
            "employee_name": "Max Mustermann",
            "employee_gender": "male",
            "employee_address": "Berlin",
            "job_title": "Clerk",
            "start_date": "2026-01-01",
            "work_location": "Office",
            "salary_type": "hourly",
            "hourly_rate": "18.50",
        },
        template=template,
        lang="de",
    )
    assert "Bruttogehalt" not in missing
    assert missing == []


def test_validate_hourly_ignores_stale_gross_monthly_in_form():
    template = {"contract_type": "employment", "required_fields_json": '["salary_gross_monthly"]'}
    missing = validate_contract_form(
        {
            "employee_name": "Max Mustermann",
            "employee_gender": "male",
            "employee_address": "Berlin",
            "job_title": "Clerk",
            "start_date": "2026-01-01",
            "work_location": "Office",
            "salary_type": "hourly",
            "hourly_rate": "18.50",
            "salary_gross_monthly": "2500",
        },
        template=template,
        lang="de",
    )
    assert "Bruttogehalt" not in missing
    assert missing == []


def test_validate_accepts_german_amount_format():
    missing = validate_contract_form(
        {
            "employee_name": "Max Mustermann",
            "employee_gender": "male",
            "employee_address": "Berlin",
            "job_title": "Clerk",
            "start_date": "2026-01-01",
            "work_location": "Office",
            "salary_gross_monthly": "2.500,00 €",
        },
        lang="de",
    )
    assert missing == []
