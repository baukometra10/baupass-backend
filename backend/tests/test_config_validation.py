import os

import pytest

from backend.app.config import ProductionConfig


def _setup_minimal_production_env(monkeypatch):
    monkeypatch.setenv("BAUPASS_ENV", "production")
    monkeypatch.setenv("BAUPASS_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/baupass")
    monkeypatch.setenv("BAUPASS_AUDIT_SIGNING_KEY", "y" * 32)
    monkeypatch.setenv("BAUPASS_ENFORCE_HTTPS", "1")
    for key in ["PUBLIC_BASE_URL", "RENDER_EXTERNAL_URL", "RAILWAY_PUBLIC_DOMAIN"]:
        monkeypatch.delenv(key, raising=False)


def test_production_validate_missing_public_base_url(monkeypatch):
    _setup_minimal_production_env(monkeypatch)
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        ProductionConfig.validate()


def test_production_validate_accepts_public_base_url(monkeypatch):
    _setup_minimal_production_env(monkeypatch)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    ProductionConfig.validate()


def test_production_validate_rejects_insecure_public_base_url(monkeypatch):
    _setup_minimal_production_env(monkeypatch)
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://example.com")
    with pytest.raises(RuntimeError, match="https"):
        ProductionConfig.validate()


def test_production_validate_allows_localhost_http_public_base_url(monkeypatch):
    _setup_minimal_production_env(monkeypatch)
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    ProductionConfig.validate()


def test_production_validate_accepts_render_external_url(monkeypatch):
    _setup_minimal_production_env(monkeypatch)
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example-render.com")
    ProductionConfig.validate()


def test_production_validate_accepts_railway_public_domain(monkeypatch):
    _setup_minimal_production_env(monkeypatch)
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "https://example-railway.app")
    ProductionConfig.validate()


def test_production_validate_allows_sqlite_with_uppercase_boolean_env(monkeypatch):
    _setup_minimal_production_env(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("BAUPASS_ALLOW_SQLITE_PRODUCTION", "YES")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    ProductionConfig.validate()
