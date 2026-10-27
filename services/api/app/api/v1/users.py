from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository, WorkerProfileRepository, OrganizationRepository
from app.schemas.user import (
    UserResponse,
    UserUpdate,
    WorkerProfileCreate,
    WorkerProfileResponse,
    WorkerProfileUpdate,
    OrganizationCreate,
    OrganizationResponse,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(user: User = Depends(get_current_user)) -> UserResponse:
    """Get the current authenticated user's profile."""
    return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
def update_current_user(
    data: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Update the current user's profile."""
    user_repo = UserRepository(db)
    user_repo.update(user, display_name=data.display_name)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


worker_profile_router = APIRouter(prefix="/worker-profiles", tags=["worker-profiles"])


@worker_profile_router.post(
    "", response_model=WorkerProfileResponse, status_code=status.HTTP_201_CREATED
)
def create_worker_profile(
    data: WorkerProfileCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkerProfileResponse:
    """Create a worker profile for the current user."""
    profile_repo = WorkerProfileRepository(db)

    # Check if profile already exists
    existing = profile_repo.get_by_user_id(user.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "duplicate", "message": "Worker profile already exists for this user"},
        )

    profile = profile_repo.create(user_id=user.id, display_name=data.display_name, bio=data.bio)
    db.commit()
    db.refresh(profile)
    return WorkerProfileResponse.model_validate(profile)


@worker_profile_router.get("/me", response_model=WorkerProfileResponse)
def get_my_worker_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkerProfileResponse:
    """Get the current user's worker profile."""
    profile_repo = WorkerProfileRepository(db)
    profile = profile_repo.get_by_user_id(user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Worker profile not found"},
        )
    return WorkerProfileResponse.model_validate(profile)


@worker_profile_router.patch("/me", response_model=WorkerProfileResponse)
def update_my_worker_profile(
    data: WorkerProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkerProfileResponse:
    """Update the current user's worker profile (cannot update onboarding_status)."""
    profile_repo = WorkerProfileRepository(db)
    profile = profile_repo.get_by_user_id(user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Worker profile not found"},
        )

    # onboarding_status is not writable by the user
    profile_repo.update(profile, display_name=data.display_name, bio=data.bio)
    db.commit()
    db.refresh(profile)
    return WorkerProfileResponse.model_validate(profile)


organization_router = APIRouter(prefix="/organizations", tags=["organizations"])


@organization_router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(
    data: OrganizationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    """Create an organization and make the current user the owner."""
    org_repo = OrganizationRepository(db)
    org, membership = org_repo.create_with_owner(
        name=data.name,
        organization_type=data.organization_type,
        owner_id=user.id,
    )
    db.commit()
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        organization_type=org.organization_type,
        my_membership_role=membership.membership_role,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@organization_router.get("/mine", response_model=list[OrganizationResponse])
def get_my_organizations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OrganizationResponse]:
    """Get organizations where the current user is a member."""
    org_repo = OrganizationRepository(db)
    memberships = org_repo.get_memberships_by_user(user.id)

    return [
        OrganizationResponse(
            id=org.id,
            name=org.name,
            organization_type=org.organization_type,
            my_membership_role=membership.membership_role,
            created_at=org.created_at,
            updated_at=org.updated_at,
        )
        for org, membership in memberships
    ]