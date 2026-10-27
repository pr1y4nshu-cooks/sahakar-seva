"""Local development identity: off by default, development-only, and never accepted when disabled."""

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.core import security
from app.core.config import Settings, get_settings
from app.core.dev_auth import DevAuthError, issue_dev_token, verify_dev_token
from app.core.security import InvalidTokenException, verify_token_against_supabase
from app.main import app

SECRET = "x" * 40
ENABLED = dict(app_env="development", dev_auth_enabled=True, dev_auth_secret=SECRET, dev_auth_passcode="demo-pass-123")


@pytest.fixture(autouse=True)
def _no_ambient_dev_auth(monkeypatch) -> None:
    # The API container exports DEV_AUTH_* for the live demo; tests must not depend on it.
    for name in ("DEV_AUTH_ENABLED", "DEV_AUTH_SECRET", "DEV_AUTH_PASSCODE", "APP_ENV"):
        monkeypatch.delenv(name, raising=False)


def test_dev_auth_is_disabled_by_default() -> None:
    assert Settings(_env_file=None).dev_auth_enabled is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_env": "production"},
        {"app_env": "staging"},
        {"dev_auth_secret": "short"},
        {"dev_auth_secret": None},
        {"dev_auth_passcode": "1234"},
    ],
)
def test_dev_auth_refuses_unsafe_configuration(overrides) -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{**ENABLED, **overrides})


def test_issue_and_verify_round_trip() -> None:
    s = Settings(_env_file=None, **ENABLED)
    token, _ = issue_dev_token(s, "Worker@Demo.Sahakar.Test", "demo-pass-123", "Asha")
    claims = verify_dev_token(s, token)
    assert claims["sub"] == "dev|worker@demo.sahakar.test"
    assert claims["email"] == "worker@demo.sahakar.test"


@pytest.mark.parametrize(
    "email,passcode",
    [("worker@demo.sahakar.test", "wrong-pass"), ("worker@gmail.com", "demo-pass-123")],
)
def test_issue_rejects_bad_passcode_or_non_demo_domain(email: str, passcode: str) -> None:
    with pytest.raises(DevAuthError):
        issue_dev_token(Settings(_env_file=None, **ENABLED), email, passcode)


def test_tokens_rejected_when_disabled_or_forged(monkeypatch) -> None:
    enabled = Settings(_env_file=None, **ENABLED)
    token, _ = issue_dev_token(enabled, "a@demo.sahakar.test", "demo-pass-123")

    monkeypatch.setattr(security, "get_settings", lambda: enabled)
    assert verify_token_against_supabase(token).sub == "dev|a@demo.sahakar.test"

    forged = jwt.encode({**jwt.get_unverified_claims(token)}, "y" * 40, algorithm="HS256")
    with pytest.raises(InvalidTokenException):
        verify_token_against_supabase(forged)

    disabled = Settings(_env_file=None, app_env="development")
    monkeypatch.setattr(security, "get_settings", lambda: disabled)
    with pytest.raises(InvalidTokenException):
        verify_token_against_supabase(token)


def test_token_endpoint_hidden_when_disabled_and_works_when_enabled() -> None:
    client = TestClient(app)
    body = {"email": "c@demo.sahakar.test", "passcode": "demo-pass-123"}
    try:
        app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, app_env="development")
        assert client.post("/api/v1/dev-auth/token", json=body).status_code == 404

        app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **ENABLED)
        ok = client.post("/api/v1/dev-auth/token", json=body)
        assert ok.status_code == 200 and ok.json()["mode"] == "local-development"
        bad = client.post("/api/v1/dev-auth/token", json={**body, "passcode": "nope-nope"})
        assert bad.status_code == 401 and bad.json()["error"]["code"] == "INVALID_CREDENTIALS"
    finally:
        app.dependency_overrides.pop(get_settings, None)
