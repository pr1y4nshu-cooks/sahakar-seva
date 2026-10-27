from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.error_handler import ContractCompliantRoute
from app.core.security import VerifiedUser, get_current_verified_user
from app.db.session import get_db
from app.schemas.organization import OrganizationCreate, OrganizationWithMyRole
from app.services.organization_service import OrganizationService
from app.services.user_service import UserService

router = APIRouter(prefix="/organizations", tags=["organizations"], route_class=ContractCompliantRoute)


@router.post(
    "",
    response_model=OrganizationWithMyRole,
    status_code=status.HTTP_201_CREATED,
    summary="Create organization with atomic owner membership",
)
def create_organization(
    payload: OrganizationCreate,
    verified_user: VerifiedUser = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> OrganizationWithMyRole:
    user = UserService.get_or_sync_user(db, verified_user)
    result = OrganizationService.create_organization_with_owner(
        db=db,
        user_id=user.id,
        name=payload.name,
        organization_type=payload.organization_type,
    )
    return OrganizationWithMyRole.model_validate(result)


@router.get(
    "/mine",
    response_model=list[OrganizationWithMyRole],
    status_code=status.HTTP_200_OK,
    summary="List caller's organizations with scoped role",
)
def list_my_organizations(
    verified_user: VerifiedUser = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> list[OrganizationWithMyRole]:
    user = UserService.get_or_sync_user(db, verified_user)
    items = OrganizationService.list_user_organizations(db, user.id)
    return [OrganizationWithMyRole.model_validate(item) for item in items]
