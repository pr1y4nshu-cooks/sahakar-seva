import os
from typing import Optional
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository

security = HTTPBearer(auto_error=False)


class SupabaseJWKS:
    def __init__(self, supabase_url: str):
        self.supabase_url = supabase_url.rstrip("/")
        self._jwks: Optional[dict] = None
        self._jwks_url = f"{self.supabase_url}/auth/v1/.well-known/jwks.json"

    async def get_jwks(self) -> dict:
        if self._jwks is None:
            async with httpx.AsyncClient() as client:
                response = await client.get(self._jwks_url, timeout=10.0)
                response.raise_for_status()
                self._jwks = response.json()
        return self._jwks

    def get_signing_key(self, kid: str) -> Optional[str]:
        if self._jwks is None:
            return None
        for key in self._jwks.get("keys", []):
            if key.get("kid") == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(str(key))
        return None


_jwks_cache: Optional[SupabaseJWKS] = None


def get_jwks_client() -> Optional[SupabaseJWKS]:
    global _jwks_cache
    settings = get_settings()
    if settings.supabase_url and _jwks_cache is None:
        _jwks_cache = SupabaseJWKS(settings.supabase_url)
    return _jwks_cache


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Validate Supabase JWT and return the current user."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Missing authorization header"},
        )

    token = credentials.credentials
    settings = get_settings()

    # If Supabase is not configured, raise 401
    if not settings.supabase_url:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Authentication not configured"},
        )

    try:
        # Get the JWKS client
        jwks_client = get_jwks_client()
        if jwks_client is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "unauthorized", "message": "JWKS client not available"},
            )

        # Decode header to get kid
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_token", "message": "Token missing key ID"},
            )

        # Get signing key
        signing_key = jwks_client.get_signing_key(kid)
        if not signing_key:
            # Try to refresh JWKS
            await jwks_client.get_jwks()
            signing_key = jwks_client.get_signing_key(kid)
            if not signing_key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"code": "invalid_token", "message": "Unable to verify token signature"},
                )

        # Decode and verify token
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience="authenticated",
            issuer=f"{settings.supabase_url}/auth/v1",
        )

        # Extract user ID from token subject
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_token", "message": "Token missing subject"},
            )

        # Get or create user
        user_repo = UserRepository(db)
        user = user_repo.get_by_external_auth_id(sub)

        if user is None:
            # Create user from token claims
            email = payload.get("email")
            display_name = payload.get("user_metadata", {}).get("display_name") or email or "User"
            if email:
                user = user_repo.create(external_auth_id=sub, display_name=display_name, email=email)
                db.commit()
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"code": "invalid_token", "message": "Token missing email"},
                )

        return user

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": f"Token validation failed: {str(e)}"},
        )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "unavailable", "message": "Authentication service unavailable"},
        )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Get current user if token is valid, otherwise return None."""
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None