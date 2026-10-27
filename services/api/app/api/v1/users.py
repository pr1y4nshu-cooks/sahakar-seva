from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.error_handler import ContractCompliantRoute
from app.core.security import VerifiedUser, get_current_verified_user
from app.db.session import get_db
from app.schemas.user import UserRead, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"], route_class=ContractCompliantRoute)


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile (idempotently syncs user with verified provider identity)",
)
def get_current_user_profile(
    verified_user: VerifiedUser = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> UserRead:
    user = UserService.get_or_sync_user(db, verified_user)
    return UserRead.model_validate(user)


@router.patch(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Update current user display name",
)
def update_current_user_profile(
    payload: UserUpdate,
    verified_user: VerifiedUser = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> UserRead:
    user = UserService.get_or_sync_user(db, verified_user)
    updated = UserService.update_display_name(db, user, payload.display_name)
    return UserRead.model_validate(updated)
