"""CODE-01 regression tests: type-safe ALLOWED_ORIGINS parsing in Settings."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def _settings(monkeypatch: pytest.MonkeyPatch, value: str | None) -> Settings:
    if value is None:
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("ALLOWED_ORIGINS", value)
    # _env_file=None isolates the test from any developer .env file
    return Settings(_env_file=None)


def test_default_origins_is_list_of_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, None)
    assert settings.allowed_origins == ["http://localhost:5173"]


def test_single_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, "http://localhost:5173")
    assert settings.allowed_origins == ["http://localhost:5173"]


def test_multiple_comma_separated_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, "http://localhost:5173,http://localhost:4173")
    assert settings.allowed_origins == ["http://localhost:5173", "http://localhost:4173"]


def test_whitespace_and_empty_segments_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, "  http://a.test , ,http://b.test  ,")
    assert settings.allowed_origins == ["http://a.test", "http://b.test"]


@pytest.mark.parametrize("value", ["", "   ", " , ,"])
def test_empty_configuration_is_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, value)


@pytest.mark.parametrize("value", ["*", "http://localhost:5173,*"])
def test_wildcard_is_rejected_because_credentials_are_allowed(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, value)


def test_python_list_input_is_accepted() -> None:
    settings = Settings(_env_file=None, allowed_origins=[" http://x.test ", "http://y.test"])
    assert settings.allowed_origins == ["http://x.test", "http://y.test"]


def test_get_settings_does_not_mutate_types() -> None:
    settings = get_settings()
    assert isinstance(settings.allowed_origins, list)
    assert all(isinstance(origin, str) for origin in settings.allowed_origins)


def test_cors_middleware_receives_list_and_preflight_works() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    allowed = get_settings().allowed_origins[0]
    with TestClient(app) as client:
        ok = client.options(
            "/api/v1/health",
            headers={"Origin": allowed, "Access-Control-Request-Method": "GET"},
        )
        assert ok.status_code == 200
        assert ok.headers.get("access-control-allow-origin") == allowed

        denied = client.options(
            "/api/v1/health",
            headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
        )
        assert denied.headers.get("access-control-allow-origin") is None
