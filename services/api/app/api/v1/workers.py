from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.error_handler import ContractCompliantRoute
from app.core.security import ResourceNotFoundException, VerifiedUser, get_current_verified_user
from app.db.session import get_db
from app.schemas.worker import WorkerProfileCreate, WorkerProfileRead, WorkerProfileUpdate
from app.services.user_service import UserService
from app.services.worker_service import WorkerService

router = APIRouter(prefix="/worker-profiles", tags=["worker-profiles"], route_class=ContractCompliantRoute)


@router.post(
    "",
    response_model=WorkerProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create initial worker profile (draft status)",
)
def create_worker_profile(
    payload: WorkerProfileCreate,
    verified_user: VerifiedUser = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> WorkerProfileRead:
    user = UserService.get_or_sync_user(db, verified_user)
    profile = WorkerService.create_worker_profile(
        db=db,
        user_id=user.id,
        display_name=payload.display_name,
        bio=payload.bio,
    )
    return WorkerProfileRead.model_validate(profile)


@router.get(
    "/me",
    response_model=WorkerProfileRead,
    status_code=status.HTTP_200_OK,
    summary="Get current user's worker profile",
)
def get_own_worker_profile(
    verified_user: VerifiedUser = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> WorkerProfileRead:
    user = UserService.get_or_sync_user(db, verified_user)
    profile = WorkerService.get_by_user_id(db, user.id)
    if not profile:
        raise ResourceNotFoundException("Worker profile not found for the current user.")
    return WorkerProfileRead.model_validate(profile)


@router.patch(
    "/me",
    response_model=WorkerProfileRead,
    status_code=status.HTTP_200_OK,
    summary="Update current user's worker profile",
)
def update_own_worker_profile(
    payload: WorkerProfileUpdate,
    verified_user: VerifiedUser = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> WorkerProfileRead:
    user = UserService.get_or_sync_user(db, verified_user)

    has_display_name = "display_name" in payload.model_fields_set
    has_bio = "bio" in payload.model_fields_set
    clear_bio = has_bio and payload.bio is None

    updated = WorkerService.update_worker_profile(
        db=db,
        user_id=user.id,
        display_name=payload.display_name if has_display_name else None,
        bio=payload.bio if (has_bio and not clear_bio) else None,
        clear_bio=clear_bio,
    )
    return WorkerProfileRead.model_validate(updated)
