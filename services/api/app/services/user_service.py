from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import IdentityConflictException, VerifiedUser
from app.models.user import User


class UserService:
    @staticmethod
    def get_or_sync_user(db: Session, verified_user: VerifiedUser) -> User:
        """
        Idempotently maps a verified Supabase identity to an application user.
        Guarantees that a subject maps to exactly one user row.
        Handles concurrent first-use and email collisions.
        """
        # 1. Check if user already exists with this external_auth_id
        stmt = select(User).where(User.external_auth_id == verified_user.sub)
        user = db.scalar(stmt)
        if user:
            return user

        # 2. Check if an existing user has the same email
        email_stmt = select(User).where(User.email == verified_user.email)
        existing_email_user = db.scalar(email_stmt)
        if existing_email_user:
            # Email exists but external_auth_id differs -> reject account takeover
            raise IdentityConflictException(
                "An existing account with this email is associated with another identity."
            )

        # 3. Create new application user
        display_name = (
            verified_user.display_name_hint
            or verified_user.email.split("@")[0][:80]
        ).strip()
        if len(display_name) < 2:
            display_name = "User " + verified_user.sub[:8]

        new_user = User(
            external_auth_id=verified_user.sub,
            email=verified_user.email,
            display_name=display_name,
        )
        db.add(new_user)
        try:
            db.commit()
            db.refresh(new_user)
            return new_user
        except IntegrityError:
            db.rollback()
            # Concurrent insert could have happened, re-fetch
            retry_stmt = select(User).where(User.external_auth_id == verified_user.sub)
            retry_user = db.scalar(retry_stmt)
            if retry_user:
                return retry_user
            raise IdentityConflictException("Conflict occurred while registering identity.")

    @staticmethod
    def update_display_name(db: Session, user: User, display_name: str) -> User:
        """Update own display name (2-80 characters trimmed)."""
        user.display_name = display_name.strip()
        db.commit()
        db.refresh(user)
        return user
