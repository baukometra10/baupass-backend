from backend.app.platform.accounting.lohn_sheet import (
    enrich_payslip_with_master,
    fill_empty_sheet_fields,
    payslip_to_sheet_data,
)


def test_fill_empty_krankenkasse_only():
    html = (
        '<span class="ds-val" id="dsv_kkName"></span>'
        '<span class="ds-val" id="dsv_persNr">1001</span>'
    )
    out = fill_empty_sheet_fields(html, {"kkName": "AOK Nordost", "persNr": "9999"})
    assert "AOK Nordost" in out
    assert ">1001<" in out
    assert "9999" not in out


def test_steuer_id_is_printed_in_full():
    payslip = {"employee": {"taxId": "88211234567", "personnelNumber": "1001"}}
    data = payslip_to_sheet_data(payslip)
    assert data["taxIdMid"] == "88211234567"
    html = '<span id="dsv_taxIdMid">8821</span>'
    out = fill_empty_sheet_fields(html, data)
    assert "88211234567" in out
    assert ">8821<" not in out


def test_datev_sheet_pdf_is_pdf_bytes():
    from backend.app.platform.accounting.lohn_sheet_pdf import render_datev_sheet_pdf

    payslip = {
        "period": "2026-08",
        "employee": {
            "name": "Feras Almohammad",
            "personnelNumber": "1001",
            "healthFund": "AOK Nordost",
            "taxId": "88211234567",
        },
        "totals": {"gross": 1200, "net": 950},
    }
    data = payslip_to_sheet_data(payslip)
    raw = render_datev_sheet_pdf(data)
    assert raw.startswith(b"%PDF")
    assert len(raw) > 800


def test_stammdaten_lock_overwrites_after_release():
    from backend.app.platform.accounting.lohn_sheet import overlay_stammdaten, snapshot_stammdaten

    payslip = {"employee": {"healthFund": "TK", "taxId": "111", "personnelNumber": "9"}}
    data = payslip_to_sheet_data(
        {"employee": {"healthFund": "AOK Nordost", "taxId": "88211234567", "personnelNumber": "1001"}}
    )
    lock = snapshot_stammdaten(data, {"employee": {"healthFund": "AOK Nordost", "taxId": "88211234567"}})
    out = overlay_stammdaten(payslip, lock, overwrite=True)
    assert out["employee"]["healthFund"] == "AOK Nordost"
    assert out["employee"]["taxId"] == "88211234567"


def test_overlay_does_not_fill_when_overwrite_false_and_live_empty():
    from backend.app.platform.accounting.lohn_sheet import overlay_stammdaten

    payslip = {"employee": {"healthFund": "AOK Nordost"}}
    out = overlay_stammdaten(payslip, {"healthFund": "TK"}, overwrite=False)
    assert out["employee"]["healthFund"] == "AOK Nordost"
    overwritten = overlay_stammdaten(payslip, {"healthFund": "TK"}, overwrite=True)
    assert overwritten["employee"]["healthFund"] == "TK"


def test_stammdaten_warnings_on_mismatch():
    from backend.app.platform.accounting.lohn_sheet import stammdaten_warnings

    warns = stammdaten_warnings(
        {"kkName": "AOK Nordost", "taxIdMid": "88211234567", "persNr": "1001"},
        {"healthFund": "TK", "taxId": "88211234567", "personnelNumber": "1001"},
    )
    assert any("Krankenkasse" in w for w in warns)
    assert not any("Steuer-ID" in w for w in warns)


def test_enrich_fills_health_fund_gap():
    payslip = {"employee": {"name": "Feras", "personnelNumber": "1001"}}
    master = {"healthFund": "AOK Nordost", "healthPercent": "8,75"}
    out = enrich_payslip_with_master(payslip, master)
    assert out["employee"]["healthFund"] == "AOK Nordost"
    data = payslip_to_sheet_data(out)
    assert data["kkName"] == "AOK Nordost"
    assert data["persNr"] == "1001"
