from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.exceptions import IdentityConflictError, UserNotFoundError


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_external_auth_id(db: Session, external_auth_id: str) -> User | None:
    return db.query(User).filter(User.external_auth_id == external_auth_id).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    normalized = email.strip().lower()
    return db.query(User).filter(func.lower(User.email) == normalized).first()


def get_or_create_user_from_verified_identity(
    db: Session,
    subject: str,
    email: str,
    display_name_hint: str,
) -> User:
    """Safely retrieves or creates an application User from a verified identity subject and email.

    Guarantees:
    - If user exists with external_auth_id == subject, returns existing user.
    - If email collides with another user (different or null external_auth_id), raises IdentityConflictError.
    - Handles concurrent first-sync race conditions gracefully via savepoints.
    """
    clean_subject = subject.strip()
    normalized_email = email.strip().lower()
    clean_display_name = display_name_hint.strip() or normalized_email.split("@")[0]

    existing_by_sub = get_user_by_external_auth_id(db, clean_subject)
    if existing_by_sub:
        return existing_by_sub

    existing_by_email = get_user_by_email(db, normalized_email)
    if existing_by_email:
        raise IdentityConflictError(
            f"Email '{normalized_email}' is already associated with another account."
        )

    user = User(
        external_auth_id=clean_subject,
        email=normalized_email,
        display_name=clean_display_name,
    )

    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        # Handle concurrent creation
        winner = get_user_by_external_auth_id(db, clean_subject)
        if winner:
            return winner
        email_collision = get_user_by_email(db, normalized_email)
        if email_collision:
            raise IdentityConflictError(
                f"Email '{normalized_email}' is already associated with another account."
            )
        raise


def update_own_user_display_name(
    db: Session,
    user_id: UUID,
    display_name: str,
) -> User:
    """Updates the display name of an existing user.

    Raises UserNotFoundError if user does not exist.
    """
    user = get_user_by_id(db, user_id)
    if not user:
        raise UserNotFoundError(f"User with id '{user_id}' not found.")

    user.display_name = display_name.strip()
    db.commit()
    db.refresh(user)
    return user

