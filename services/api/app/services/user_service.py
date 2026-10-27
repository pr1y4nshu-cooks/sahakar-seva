from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import IdentityConflictException, ResourceNotFoundException, VerifiedUser
from app.models.user import User
from app.repositories import user_repository
from app.repositories.exceptions import IdentityConflictError, UserNotFoundError


class UserService:
    """Business rules for the current user. Persistence is delegated to app.repositories.user_repository."""

    @staticmethod
    def _display_name_for(verified_user: VerifiedUser) -> str:
        display_name = (
            verified_user.display_name_hint or verified_user.email.split("@")[0]
        ).strip()[:80]
        if len(display_name) < 2:
            display_name = "User " + verified_user.sub[:8]
        return display_name

    @staticmethod
    def get_or_sync_user(db: Session, verified_user: VerifiedUser) -> User:
        """
        Idempotently maps a verified Supabase identity to an application user.
        Guarantees that a subject maps to exactly one user row.
        Handles concurrent first-use and email collisions (HTTP 409 IDENTITY_CONFLICT).
        """
        try:
            return user_repository.get_or_create_user_from_verified_identity(
                db,
                subject=verified_user.sub,
                email=verified_user.email,
                display_name_hint=UserService._display_name_for(verified_user),
            )
        except IdentityConflictError as exc:
            # Repository message contains the email; do not echo it back to the client.
            raise IdentityConflictException(
                "An existing account with this email is associated with another identity."
            ) from exc
        except IntegrityError as exc:
            raise IdentityConflictException("Conflict occurred while registering identity.") from exc

    @staticmethod
    def update_display_name(db: Session, user: User, display_name: str) -> User:
        """Update own display name (2-80 characters trimmed)."""
        try:
            return user_repository.update_own_user_display_name(db, user.id, display_name)
        except UserNotFoundError as exc:
            raise ResourceNotFoundException("User not found.") from exc
