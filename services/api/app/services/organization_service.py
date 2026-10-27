from typing import Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization, OrganizationMembership


class OrganizationService:
    @staticmethod
    def create_organization_with_owner(
        db: Session,
        user_id: UUID,
        name: str,
        organization_type: str,
        _membership_failure_hook: Any = None,
    ) -> dict[str, Any]:
        """
        Creates an organization and its creator's owner membership in a single transaction.
        If any step fails, both are rolled back.
        """
        try:
            # 1. Create Organization
            org = Organization(
                name=name.strip(),
                organization_type=organization_type,
            )
            db.add(org)
            db.flush()  # assign org.id within transaction

            # Failure hook for transaction atomicity negative testing
            if _membership_failure_hook:
                _membership_failure_hook()

            # 2. Create Owner Membership
            membership = OrganizationMembership(
                organization_id=org.id,
                user_id=user_id,
                membership_role="owner",
            )
            db.add(membership)
            db.commit()
            db.refresh(org)

            return {
                "id": org.id,
                "name": org.name,
                "organization_type": org.organization_type,
                "my_membership_role": "owner",
                "created_at": org.created_at,
                "updated_at": org.updated_at,
            }
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def list_user_organizations(db: Session, user_id: UUID) -> list[dict[str, Any]]:
        """
        Lists only the caller's organizations with their scoped membership role.
        Never discloses other users' organizations.
        """
        stmt = (
            select(Organization, OrganizationMembership.membership_role)
            .join(OrganizationMembership, Organization.id == OrganizationMembership.organization_id)
            .where(OrganizationMembership.user_id == user_id)
            .order_by(Organization.created_at.desc())
        )
        results = db.execute(stmt).all()

        return [
            {
                "id": org.id,
                "name": org.name,
                "organization_type": org.organization_type,
                "my_membership_role": role,
                "created_at": org.created_at,
                "updated_at": org.updated_at,
            }
            for org, role in results
        ]
