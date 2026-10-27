import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User, WorkerProfile
from app.repositories.exceptions import (
    WorkerProfileExistsError,
    WorkerProfileNotFoundError,
)
from app.repositories.user_repository import get_or_create_user_from_verified_identity
from app.repositories.worker_repository import (
    create_worker_profile_for_user,
    get_worker_profile_by_user,
    update_worker_profile_for_user,
)


def _create_test_user(db: Session) -> User:
    sub = f"sub_{uuid.uuid4()}"
    email = f"user_{uuid.uuid4()}@example.com"
    return get_or_create_user_from_verified_identity(
        db, subject=sub, email=email, display_name_hint="Test User"
    )


def test_create_worker_profile_creates_draft(db: Session) -> None:
    user = _create_test_user(db)
    profile = create_worker_profile_for_user(
        db, user_id=user.id, display_name="Electrician Worker", bio="5 years experience"
    )

    assert profile is not None
    assert profile.user_id == user.id
    assert profile.display_name == "Electrician Worker"
    assert profile.bio == "5 years experience"
    assert profile.onboarding_status == "draft"

    # Verify persisted in DB
    fetched = get_worker_profile_by_user(db, user.id)
    assert fetched is not None
    assert fetched.id == profile.id
    assert fetched.onboarding_status == "draft"


def test_create_worker_profile_duplicate_raises_conflict(db: Session) -> None:
    user = _create_test_user(db)
    create_worker_profile_for_user(
        db, user_id=user.id, display_name="Worker One", bio=None
    )

    with pytest.raises(WorkerProfileExistsError):
        create_worker_profile_for_user(
            db, user_id=user.id, display_name="Worker Two", bio="Duplicate attempt"
        )


def test_get_worker_profile_by_user_not_found(db: Session) -> None:
    random_user_id = uuid.uuid4()
    profile = get_worker_profile_by_user(db, random_user_id)
    assert profile is None


def test_update_worker_profile_fields(db: Session) -> None:
    user = _create_test_user(db)
    profile = create_worker_profile_for_user(
        db, user_id=user.id, display_name="Initial Name", bio="Initial Bio"
    )

    updated = update_worker_profile_for_user(
        db, user_id=user.id, display_name="New Name", bio="New Bio"
    )
    assert updated.display_name == "New Name"
    assert updated.bio == "New Bio"
    assert updated.onboarding_status == "draft"  # Status remains draft!


def test_update_worker_profile_clear_bio(db: Session) -> None:
    user = _create_test_user(db)
    create_worker_profile_for_user(
        db, user_id=user.id, display_name="Worker Name", bio="Existing Bio"
    )

    updated = update_worker_profile_for_user(
        db, user_id=user.id, clear_bio=True
    )
    assert updated.bio is None
    assert updated.display_name == "Worker Name"


def test_update_worker_profile_not_found_raises(db: Session) -> None:
    random_id = uuid.uuid4()
    with pytest.raises(WorkerProfileNotFoundError):
        update_worker_profile_for_user(
            db, user_id=random_id, display_name="Nonexistent"
        )


def test_worker_profile_db_check_constraint_rejects_invalid_status(db: Session) -> None:
    user = _create_test_user(db)
    invalid_profile = WorkerProfile(
        user_id=user.id,
        display_name="Hacker",
        onboarding_status="super_approved",  # Not in ('draft', 'pending_review', 'approved', 'restricted')
    )
    db.add(invalid_profile)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
