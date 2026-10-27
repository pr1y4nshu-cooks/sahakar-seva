"""Local development identity provider (MVP_MARKETPLACE_CONTRACT §9).

Issues short-lived HS256 tokens for disposable demo identities when Supabase credentials are not
available. It is disabled by default, refused outside APP_ENV=development (see Settings), signed
with a secret separate from any Supabase secret, and its tokens are rejected whenever it is off.
"""

import hmac
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import Settings

DEV_ISSUER = "sahakar-dev-auth"
DEV_AUDIENCE = "authenticated"
DEV_TOKEN_TTL = timedelta(hours=8)
DEV_SUBJECT_PREFIX = "dev|"


class DevAuthError(Exception):
    pass


def is_dev_token(token: str) -> bool:
    try:
        return jwt.get_unverified_claims(token).get("iss") == DEV_ISSUER
    except JWTError:
        return False


def issue_dev_token(settings: Settings, email: str, passcode: str, display_name: str | None = None) -> tuple[str, datetime]:
    if not settings.dev_auth_enabled:
        raise DevAuthError("Development authentication is disabled.")
    normalized = email.strip().lower()
    if not normalized.endswith("@" + settings.dev_auth_email_domain.lower()):
        raise DevAuthError(f"Demo identities must use an @{settings.dev_auth_email_domain} email address.")
    if not hmac.compare_digest(passcode.encode(), (settings.dev_auth_passcode or "").encode()):
        raise DevAuthError("Invalid demo passcode.")
    now = datetime.now(timezone.utc)
    expires = now + DEV_TOKEN_TTL
    claims = {
        "iss": DEV_ISSUER,
        "aud": DEV_AUDIENCE,
        "sub": DEV_SUBJECT_PREFIX + normalized,
        "email": normalized,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "user_metadata": {"display_name": display_name} if display_name else {},
    }
    return jwt.encode(claims, settings.dev_auth_secret, algorithm="HS256"), expires


def verify_dev_token(settings: Settings, token: str) -> dict:
    if not settings.dev_auth_enabled or not settings.dev_auth_secret:
        raise DevAuthError("Development tokens are not accepted because dev auth is disabled.")
    try:
        claims = jwt.decode(
            token, settings.dev_auth_secret, algorithms=["HS256"], audience=DEV_AUDIENCE, issuer=DEV_ISSUER
        )
    except JWTError as exc:
        raise DevAuthError(f"Development token verification failed: {exc}") from exc
    if not str(claims.get("sub", "")).startswith(DEV_SUBJECT_PREFIX) or not claims.get("email"):
        raise DevAuthError("Development token is missing identity claims.")
    return claims
