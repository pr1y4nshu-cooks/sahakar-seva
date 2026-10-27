import os
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import get_settings


@dataclass
class VerifiedUser:
    sub: str
    email: str
    display_name_hint: str | None = None


class AuthException(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None):
        super().__init__(
            status_code=status_code,
            detail={"error": {"code": code, "message": message, "details": details}},
        )


class AuthRequiredException(AuthException):
    def __init__(self, message: str = "Authentication credentials were not provided."):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, code="AUTH_REQUIRED", message=message)


class InvalidTokenException(AuthException):
    def __init__(self, message: str = "Invalid, expired, or malformed authentication token."):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, code="INVALID_TOKEN", message=message)


class AuthProviderUnavailableException(AuthException):
    def __init__(self, message: str = "Authentication provider is temporarily unavailable."):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_PROVIDER_UNAVAILABLE",
            message=message,
        )


class AuthNotConfiguredException(AuthException):
    def __init__(self, message: str = "Authentication provider is not configured."):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_NOT_CONFIGURED",
            message=message,
        )


class IdentityConflictException(AuthException):
    def __init__(self, message: str = "An existing account with this email is associated with another identity."):
        super().__init__(status_code=status.HTTP_409_CONFLICT, code="IDENTITY_CONFLICT", message=message)


class WorkerProfileExistsException(AuthException):
    def __init__(self, message: str = "Worker profile already exists for this user."):
        super().__init__(status_code=status.HTTP_409_CONFLICT, code="WORKER_PROFILE_EXISTS", message=message)


class ResourceNotFoundException(AuthException):
    def __init__(self, message: str = "The requested resource was not found."):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, code="RESOURCE_NOT_FOUND", message=message)


http_bearer = HTTPBearer(auto_error=False)


def verify_token_against_supabase(token: str) -> VerifiedUser:
    """
    Verify Supabase bearer access token.
    Supports:
    1. HS256 JWT cryptographic signature verification when SUPABASE_JWT_SECRET is configured.
    2. Server-side Supabase Auth API get_user(token) validation when SUPABASE_URL is configured.
    3. Fails closed (503) if network/provider is unavailable or unconfigured.
    """
    settings = get_settings()
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")

    # Mode A: Shared secret / HS256 cryptographic verification
    if jwt_secret:
        try:
            # Reject 'none' or mismatched algorithms
            unverified_header = jwt.get_unverified_header(token)
            if unverified_header.get("alg") not in ["HS256", "RS256"]:
                raise InvalidTokenException("Unsupported token signing algorithm.")

            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": True, "verify_exp": True},
                audience="authenticated",
            )
            sub = payload.get("sub")
            email = payload.get("email")
            if not sub or not email:
                raise InvalidTokenException("Token payload missing required identity claims.")

            metadata = payload.get("user_metadata") or {}
            display_name = metadata.get("display_name") or metadata.get("name") or metadata.get("full_name")
            return VerifiedUser(sub=str(sub), email=str(email), display_name_hint=display_name)
        except JWTError as exc:
            raise InvalidTokenException(f"Token verification failed: {exc}") from exc

    # Mode B: Server-side validation against Supabase Auth get_user API
    supabase_url = settings.supabase_url or os.getenv("SUPABASE_URL")
    supabase_anon_key = settings.supabase_anon_key or os.getenv("SUPABASE_ANON_KEY")

    if supabase_url and supabase_anon_key:
        endpoint = f"{supabase_url.rstrip('/')}/auth/v1/user"
        headers = {
            "Authorization": f"Bearer {token}",
            "apikey": supabase_anon_key,
        }
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(endpoint, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AuthProviderUnavailableException("Could not connect to authentication provider.") from exc
        except Exception as exc:
            raise AuthProviderUnavailableException("Authentication provider call failed.") from exc

        if response.status_code == 200:
            user_data = response.json()
            sub = user_data.get("id")
            email = user_data.get("email")
            if not sub or not email:
                raise InvalidTokenException("Authentication provider returned incomplete user identity.")
            metadata = user_data.get("user_metadata") or {}
            display_name = metadata.get("display_name") or metadata.get("name") or metadata.get("full_name")
            return VerifiedUser(sub=str(sub), email=str(email), display_name_hint=display_name)
        elif response.status_code in {400, 401, 403}:
            raise InvalidTokenException("Authentication token is invalid or expired.")
        else:
            raise AuthProviderUnavailableException(f"Authentication provider returned status {response.status_code}.")

    # If neither is configured, fail closed
    raise AuthNotConfiguredException("Authentication provider is not configured.")


# Verifier hook that can be overridden in tests via dependency overrides
verify_supabase_token = verify_token_against_supabase


def get_token_verifier() -> Callable[[str], VerifiedUser]:
    return verify_token_against_supabase


def get_current_verified_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    verifier: Callable[[str], VerifiedUser] = Depends(get_token_verifier),
) -> VerifiedUser:
    if not credentials or not credentials.credentials:
        raise AuthRequiredException("Authorization bearer token is required.")

    token = credentials.credentials.strip()
    if not token:
        raise AuthRequiredException("Authorization bearer token cannot be blank.")

    return verifier(token)
