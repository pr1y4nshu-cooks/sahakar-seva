from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import WorkerProfile
from app.repositories.exceptions import (
    WorkerProfileExistsError,
    WorkerProfileNotFoundError,
)


def get_worker_profile_by_user(db: Session, user_id: UUID) -> WorkerProfile | None:
    """Retrieves worker profile for a given user, or None if not found."""
    return db.query(WorkerProfile).filter(WorkerProfile.user_id == user_id).first()


def create_worker_profile_for_user(
    db: Session,
    user_id: UUID,
    display_name: str,
    bio: str | None = None,
) -> WorkerProfile:
    """Creates a worker profile for user with initial status 'draft'.

    Raises WorkerProfileExistsError if a profile already exists for user.
    """
    existing = get_worker_profile_by_user(db, user_id)
    if existing:
        raise WorkerProfileExistsError(
            f"Worker profile already exists for user '{user_id}'."
        )

    clean_bio = bio.strip() if bio is not None and bio.strip() else None
    profile = WorkerProfile(
        user_id=user_id,
        display_name=display_name.strip(),
        bio=clean_bio,
        onboarding_status="draft",
    )

    try:
        with db.begin_nested():
            db.add(profile)
            db.flush()
        db.commit()
        db.refresh(profile)
        return profile
    except IntegrityError as exc:
        db.rollback()
        # If another request created it concurrently
        if get_worker_profile_by_user(db, user_id):
            raise WorkerProfileExistsError(
                f"Worker profile already exists for user '{user_id}'."
            ) from exc
        raise


def update_worker_profile_for_user(
    db: Session,
    user_id: UUID,
    display_name: str | None = None,
    bio: str | None = None,
    clear_bio: bool = False,
) -> WorkerProfile:
    """Updates editable fields (display_name, bio) of a worker profile.

    Status fields are strictly immutable via this method.
    Raises WorkerProfileNotFoundError if profile does not exist.
    """
    profile = get_worker_profile_by_user(db, user_id)
    if not profile:
        raise WorkerProfileNotFoundError(
            f"Worker profile not found for user '{user_id}'."
        )

    if display_name is not None and display_name.strip():
        profile.display_name = display_name.strip()

    if clear_bio:
        profile.bio = None
    elif bio is not None:
        profile.bio = bio.strip() if bio.strip() else None

    db.commit()
    db.refresh(profile)
    return profile
