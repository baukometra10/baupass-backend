from backend.app.platform.ai.openai_errors import parse_openai_http_error
from backend.app.platform.ai.whisper import list_whisper_providers


def test_parse_insufficient_quota_json():
    detail = (
        '{"error":{"message":"You exceeded your current quota, please check your plan and billing details.",'
        '"type":"insufficient_quota","param":null,"code":"insufficient_quota"}}'
    )
    out = parse_openai_http_error(detail)
    assert out["error"] == "openai_quota_exceeded"
    assert "billing" in out["hint"].lower()


def test_parse_invalid_api_key():
    detail = '{"error":{"message":"Incorrect API key provided","type":"invalid_request_error","code":"invalid_api_key"}}'
    out = parse_openai_http_error(detail)
    assert out["error"] == "openai_auth_error"


def test_whisper_prefers_azure_when_configured(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    providers = list_whisper_providers()
    assert len(providers) == 2
    assert providers[0].provider == "azure"
    assert providers[1].provider == "openai"
