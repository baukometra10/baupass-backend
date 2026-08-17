"""ONVIF probe helpers — host parse, no network."""
from backend.app.platform.physical_operations.onvif_probe import parse_onvif_host, probe_onvif


def test_parse_onvif_host_plain():
    host, port, https = parse_onvif_host("192.168.1.20")
    assert host == "192.168.1.20"
    assert port == 80
    assert https is False


def test_parse_onvif_host_https_port():
    host, port, https = parse_onvif_host("https://cam.local:8443/onvif")
    assert host == "cam.local"
    assert port == 8443
    assert https is True


def test_probe_rejects_invalid_host():
    out = probe_onvif("http://evil")
    assert out.get("ok") is False
    assert out.get("error") == "invalid_host"
