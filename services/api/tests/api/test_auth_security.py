import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.orm import Session

from app.core.security import (
    AuthProviderUnavailableException,
    InvalidTokenException,
    VerifiedUser,
    get_token_verifier,
    verify_supabase_token,
)
from app.main import app
from app.models.user import User


def test_missing_auth_header_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "AUTH_REQUIRED"


def test_blank_bearer_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/users/me", headers={"Authorization": "Bearer   "})
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "AUTH_REQUIRED"


def test_invalid_token_returns_401(client: TestClient) -> None:
    def fake_verifier(token: str) -> VerifiedUser:
        raise InvalidTokenException("Invalid token signature or expired.")

    app.dependency_overrides[get_token_verifier] = lambda: fake_verifier
    try:
        response = client.get("/api/v1/users/me", headers={"Authorization": "Bearer bad_token"})
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "INVALID_TOKEN"
    finally:
        app.dependency_overrides.pop(get_token_verifier, None)


def test_provider_unavailable_returns_503(client: TestClient) -> None:
    def unavailable_verifier(token: str) -> VerifiedUser:
        raise AuthProviderUnavailableException("Auth provider unreachable.")

    app.dependency_overrides[get_token_verifier] = lambda: unavailable_verifier
    try:
        response = client.get("/api/v1/users/me", headers={"Authorization": "Bearer token"})
        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "AUTH_PROVIDER_UNAVAILABLE"
    finally:
        app.dependency_overrides.pop(get_token_verifier, None)


def test_jwt_cryptographic_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test-secret-32-bytes-minimum-length-needed-here!"
    monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)

    # Valid token
    payload = {
        "sub": "user_123",
        "email": "user123@example.com",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
        "user_metadata": {"display_name": "Test User"},
    }
    valid_token = jwt.encode(payload, secret, algorithm="HS256")
    verified = verify_supabase_token(valid_token)
    assert verified.sub == "user_123"
    assert verified.email == "user123@example.com"
    assert verified.display_name_hint == "Test User"

    # Expired token
    expired_payload = dict(payload, exp=int(time.time()) - 3600)
    expired_token = jwt.encode(expired_payload, secret, algorithm="HS256")
    with pytest.raises(InvalidTokenException):
        verify_supabase_token(expired_token)

    # Wrong audience
    wrong_aud_payload = dict(payload, aud="wrong_aud")
    wrong_aud_token = jwt.encode(wrong_aud_payload, secret, algorithm="HS256")
    with pytest.raises(InvalidTokenException):
        verify_supabase_token(wrong_aud_token)

    # Tampered token
    tampered_token = valid_token[:-4] + "xxxx"
    with pytest.raises(InvalidTokenException):
        verify_supabase_token(tampered_token)


def test_identity_conflict_on_email_collision(client: TestClient, db_session: Session) -> None:
    # Pre-populate a user with email 'alice@example.com' and sub 'sub_alice'
    existing = User(
        external_auth_id="sub_alice",
        email="alice@example.com",
        display_name="Alice",
    )
    db_session.add(existing)
    db_session.commit()

    # Now an incoming token claims email 'alice@example.com' with DIFFERENT sub 'sub_attacker'
    def collision_verifier(token: str) -> VerifiedUser:
        return VerifiedUser(sub="sub_attacker", email="alice@example.com", display_name_hint="Attacker")

    app.dependency_overrides[get_token_verifier] = lambda: collision_verifier
    try:
        response = client.get("/api/v1/users/me", headers={"Authorization": "Bearer token"})
        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "IDENTITY_CONFLICT"
    finally:
        app.dependency_overrides.pop(get_token_verifier, None)
