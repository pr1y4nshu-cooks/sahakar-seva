from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import ResourceNotFoundException, WorkerProfileExistsException
from app.models.user import WorkerProfile


class WorkerService:
    @staticmethod
    def get_by_user_id(db: Session, user_id: UUID) -> WorkerProfile | None:
        """Get worker profile for given user_id."""
        stmt = select(WorkerProfile).where(WorkerProfile.user_id == user_id)
        return db.scalar(stmt)

    @staticmethod
    def create_worker_profile(
        db: Session, user_id: UUID, display_name: str, bio: str | None = None
    ) -> WorkerProfile:
        """
        Creates the worker profile for the authenticated user with initial status 'draft'.
        Raises WorkerProfileExistsException if user already has a profile.
        """
        # 1. Pre-check existing profile
        existing = WorkerService.get_by_user_id(db, user_id)
        if existing:
            raise WorkerProfileExistsException("Worker profile already exists for this user.")

        # 2. Insert new profile with status 'draft'
        profile = WorkerProfile(
            user_id=user_id,
            display_name=display_name.strip(),
            bio=bio,
            onboarding_status="draft",
        )
        db.add(profile)
        try:
            db.commit()
            db.refresh(profile)
            return profile
        except IntegrityError as exc:
            db.rollback()
            raise WorkerProfileExistsException("Worker profile already exists for this user.") from exc

    @staticmethod
    def update_worker_profile(
        db: Session,
        user_id: UUID,
        display_name: str | None = None,
        bio: str | None = None,
        clear_bio: bool = False,
    ) -> WorkerProfile:
        """
        Updates own worker profile display_name and/or bio.
        Cannot modify onboarding_status, user_id, or privileged fields.
        """
        profile = WorkerService.get_by_user_id(db, user_id)
        if not profile:
            raise ResourceNotFoundException("Worker profile does not exist.")

        if display_name is not None:
            profile.display_name = display_name.strip()

        if clear_bio:
            profile.bio = None
        elif bio is not None:
            profile.bio = bio

        db.commit()
        db.refresh(profile)
        return profile
