from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.repositories import organization_repository


def _to_response(org: Organization, role: str) -> dict[str, Any]:
    return {
        "id": org.id,
        "name": org.name,
        "organization_type": org.organization_type,
        "my_membership_role": role,
        "created_at": org.created_at,
        "updated_at": org.updated_at,
    }


class OrganizationService:
    """Organization rules. Persistence is delegated to app.repositories.organization_repository."""

    @staticmethod
    def create_organization_with_owner(
        db: Session,
        user_id: UUID,
        name: str,
        organization_type: str,
    ) -> dict[str, Any]:
        """
        Creates an organization and its creator's owner membership in a single transaction
        (one commit inside the repository). If any step fails, both are rolled back.
        """
        org, membership = organization_repository.create_organization_with_owner(
            db, user_id=user_id, name=name, organization_type=organization_type
        )
        return _to_response(org, membership.membership_role)

    @staticmethod
    def list_user_organizations(db: Session, user_id: UUID) -> list[dict[str, Any]]:
        """
        Lists only the caller's organizations with their scoped membership role.
        Never discloses other users' organizations.
        """
        return [
            _to_response(org, role)
            for org, role in organization_repository.list_organizations_for_user(db, user_id)
        ]
