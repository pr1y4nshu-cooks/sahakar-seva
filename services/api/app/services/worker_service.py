from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import ResourceNotFoundException, WorkerProfileExistsException
from app.models.user import WorkerProfile
from app.repositories import worker_repository
from app.repositories.exceptions import WorkerProfileExistsError, WorkerProfileNotFoundError


class WorkerService:
    """Worker-profile rules. Persistence is delegated to app.repositories.worker_repository."""

    @staticmethod
    def get_by_user_id(db: Session, user_id: UUID) -> WorkerProfile | None:
        """Get worker profile for given user_id."""
        return worker_repository.get_worker_profile_by_user(db, user_id)

    @staticmethod
    def create_worker_profile(
        db: Session, user_id: UUID, display_name: str, bio: str | None = None
    ) -> WorkerProfile:
        """
        Creates the worker profile for the authenticated user with initial status 'draft'
        (enforced by the repository). Raises WorkerProfileExistsException (409) on duplicates.
        """
        try:
            return worker_repository.create_worker_profile_for_user(
                db, user_id=user_id, display_name=display_name, bio=bio
            )
        except WorkerProfileExistsError as exc:
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
        try:
            return worker_repository.update_worker_profile_for_user(
                db, user_id=user_id, display_name=display_name, bio=bio, clear_bio=clear_bio
            )
        except WorkerProfileNotFoundError as exc:
            raise ResourceNotFoundException("Worker profile does not exist.") from exc
