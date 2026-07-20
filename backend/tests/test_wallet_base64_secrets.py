"""Wallet signing accepts Railway-friendly base64 cert secrets."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from backend import server


def test_wallet_apple_p12_bytes_from_base64(monkeypatch):
    raw = b"pkcs12-bytes-here"
    import base64

    monkeypatch.setenv("APPLE_CERT_BASE64", base64.b64encode(raw).decode("ascii"))
    monkeypatch.delenv("APPLE_CERT_PATH", raising=False)
    assert server._wallet_apple_p12_bytes() == raw


def test_wallet_collect_runtime_status_accepts_base64_without_path(monkeypatch):
    monkeypatch.setenv("APPLE_CERT_BASE64", "YQ==")
    monkeypatch.setenv("APPLE_CERT_PASSWORD", "x")
    monkeypatch.delenv("APPLE_CERT_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_ISSUER_ID", raising=False)

    with (
        patch.object(server, "_wallet_load_apple_signing_material", side_effect=RuntimeError("no real cert")),
        patch.object(server, "_wallet_load_google_service_account", side_effect=RuntimeError("no google")),
    ):
        status = server._wallet_collect_runtime_status()

    assert "APPLE_CERT_PATH|APPLE_CERT_BASE64" not in status["missing"]["apple"]
    assert status["files"]["APPLE_CERT_BASE64"]["configured"] is True
