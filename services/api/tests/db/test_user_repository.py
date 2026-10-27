import uuid
import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.exceptions import IdentityConflictError, UserNotFoundError
from app.repositories.user_repository import (
    get_or_create_user_from_verified_identity,
    get_user_by_email,
    get_user_by_external_auth_id,
    get_user_by_id,
    update_own_user_display_name,
)


def test_get_or_create_user_creates_new(db: Session) -> None:
    subject = f"sub_{uuid.uuid4()}"
    email = f"user_{uuid.uuid4()}@example.com"
    display_name = "New Worker"

    user = get_or_create_user_from_verified_identity(
        db, subject=subject, email=email, display_name_hint=display_name
    )

    assert user is not None
    assert user.id is not None
    assert user.external_auth_id == subject
    assert user.email == email.lower()
    assert user.display_name == display_name

    # Verify persisted in database
    fetched = get_user_by_id(db, user.id)
    assert fetched is not None
    assert fetched.external_auth_id == subject


def test_get_or_create_user_returns_existing_idempotent(db: Session) -> None:
    subject = f"sub_{uuid.uuid4()}"
    email = f"user_{uuid.uuid4()}@example.com"
    display_name = "First Name"

    user1 = get_or_create_user_from_verified_identity(
        db, subject=subject, email=email, display_name_hint=display_name
    )
    user2 = get_or_create_user_from_verified_identity(
        db, subject=subject, email=email, display_name_hint="Different Name"
    )

    assert user1.id == user2.id
    assert user2.external_auth_id == subject


def test_get_or_create_user_raises_identity_conflict(db: Session) -> None:
    email = f"conflict_{uuid.uuid4()}@example.com"
    subject1 = f"sub_{uuid.uuid4()}"
    subject2 = f"sub_{uuid.uuid4()}"

    # First user owns the email
    get_or_create_user_from_verified_identity(
        db, subject=subject1, email=email, display_name_hint="User One"
    )

    # Different verified subject attempting to use the same email must raise IdentityConflictError
    with pytest.raises(IdentityConflictError):
        get_or_create_user_from_verified_identity(
            db, subject=subject2, email=email, display_name_hint="User Two"
        )


def test_update_own_user_display_name_success(db: Session) -> None:
    subject = f"sub_{uuid.uuid4()}"
    email = f"user_{uuid.uuid4()}@example.com"
    user = get_or_create_user_from_verified_identity(
        db, subject=subject, email=email, display_name_hint="Original Name"
    )

    updated = update_own_user_display_name(db, user_id=user.id, display_name="Updated Name")
    assert updated.display_name == "Updated Name"

    # Verify persisted
    refetched = get_user_by_id(db, user.id)
    assert refetched is not None
    assert refetched.display_name == "Updated Name"


def test_update_own_user_display_name_not_found(db: Session) -> None:
    random_id = uuid.uuid4()
    with pytest.raises(UserNotFoundError):
        update_own_user_display_name(db, user_id=random_id, display_name="Ghost")


def test_get_user_by_email_and_external_auth_id(db: Session) -> None:
    subject = f"sub_{uuid.uuid4()}"
    email = f"lookup_{uuid.uuid4()}@example.com"
    user = get_or_create_user_from_verified_identity(
        db, subject=subject, email=email, display_name_hint="Lookup User"
    )

    by_email = get_user_by_email(db, email.upper())
    assert by_email is not None
    assert by_email.id == user.id

    by_sub = get_user_by_external_auth_id(db, subject)
    assert by_sub is not None
    assert by_sub.id == user.id
