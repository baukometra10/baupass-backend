from backend.app.platform.ai.whisper import _parse_openai_http_error


def test_parse_insufficient_quota_json():
    detail = (
        '{"error":{"message":"You exceeded your current quota, please check your plan and billing details.",'
        '"type":"insufficient_quota","param":null,"code":"insufficient_quota"}}'
    )
    out = _parse_openai_http_error(detail)
    assert out["error"] == "openai_quota_exceeded"
    assert "billing" in out["hint"].lower()


def test_parse_invalid_api_key():
    detail = '{"error":{"message":"Incorrect API key provided","type":"invalid_request_error","code":"invalid_api_key"}}'
    out = _parse_openai_http_error(detail)
    assert out["error"] == "openai_auth_error"
