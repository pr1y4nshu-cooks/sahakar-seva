"""SEC-02 regression tests: verification configuration and fail-closed behaviour."""

import time

import pytest
from jose import jwt

from app.core import security
from app.core.config import Settings
from app.core.security import (
    AuthNotConfiguredException,
    InvalidTokenException,
    verify_token_against_supabase,
)

SECRET = "settings-secret-32-bytes-minimum-length-for-tests!"


def _payload(**overrides) -> dict:
    base = {
        "sub": "user_cfg",
        "email": "cfg@example.com",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    base.update(overrides)
    return base


@pytest.fixture
def isolated_settings(monkeypatch: pytest.MonkeyPatch):
    """Point the verifier at an explicit Settings object, independent of any developer .env."""
    for name in ("SUPABASE_JWT_SECRET", "SUPABASE_URL", "SUPABASE_ANON_KEY"):
        monkeypatch.delenv(name, raising=False)

    def _apply(**values) -> Settings:
        settings = Settings(_env_file=None, **values)
        monkeypatch.setattr(security, "get_settings", lambda: settings)
        return settings

    return _apply


def test_missing_verification_configuration_fails_closed(isolated_settings) -> None:
    isolated_settings()
    token = jwt.encode(_payload(), SECRET, algorithm="HS256")
    with pytest.raises(AuthNotConfiguredException) as exc:
        verify_token_against_supabase(token)
    assert exc.value.status_code == 503


def test_jwt_secret_from_settings_is_used(isolated_settings) -> None:
    isolated_settings(supabase_jwt_secret=SECRET)
    token = jwt.encode(_payload(), SECRET, algorithm="HS256")
    verified = verify_token_against_supabase(token)
    assert verified.sub == "user_cfg"


def test_wrong_secret_is_rejected(isolated_settings) -> None:
    isolated_settings(supabase_jwt_secret=SECRET)
    forged = jwt.encode(_payload(), "attacker-secret-that-is-also-long-enough!!", algorithm="HS256")
    with pytest.raises(InvalidTokenException):
        verify_token_against_supabase(forged)


def test_unsigned_alg_none_token_is_rejected(isolated_settings) -> None:
    isolated_settings(supabase_jwt_secret=SECRET)
    import base64
    import json

    def b64(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(_payload())}."
    with pytest.raises(InvalidTokenException):
        verify_token_against_supabase(unsigned)


def test_token_missing_identity_claims_is_rejected(isolated_settings) -> None:
    isolated_settings(supabase_jwt_secret=SECRET)
    payload = _payload()
    payload.pop("email")
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    with pytest.raises(InvalidTokenException):
        verify_token_against_supabase(token)


def test_error_message_does_not_echo_secret(isolated_settings) -> None:
    isolated_settings(supabase_jwt_secret=SECRET)
    with pytest.raises(InvalidTokenException) as exc:
        verify_token_against_supabase("not-a-jwt")
    assert SECRET not in str(exc.value.detail)
