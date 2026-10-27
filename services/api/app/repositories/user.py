from uuid import UUID
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, WorkerProfile
from app.models.organization import Organization, OrganizationMembership


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_external_auth_id(self, external_auth_id: str) -> Optional[User]:
        return self.db.execute(
            select(User).where(User.external_auth_id == external_auth_id)
        ).scalar_one_or_none()

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

    def get_by_id(self, user_id: UUID) -> Optional[User]:
        return self.db.get(User, user_id)

    def create(self, external_auth_id: str, display_name: str, email: str) -> User:
        user = User(
            external_auth_id=external_auth_id,
            display_name=display_name,
            email=email,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def update(self, user: User, display_name: Optional[str] = None) -> User:
        if display_name is not None:
            user.display_name = display_name
        self.db.flush()
        return user


class WorkerProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user_id(self, user_id: UUID) -> Optional[WorkerProfile]:
        return self.db.execute(
            select(WorkerProfile).where(WorkerProfile.user_id == user_id)
        ).scalar_one_or_none()

    def get_by_id(self, profile_id: UUID) -> Optional[WorkerProfile]:
        return self.db.get(WorkerProfile, profile_id)

    def create(self, user_id: UUID, display_name: str, bio: Optional[str] = None) -> WorkerProfile:
        profile = WorkerProfile(
            user_id=user_id,
            display_name=display_name,
            bio=bio,
            onboarding_status="draft",
        )
        self.db.add(profile)
        self.db.flush()
        return profile

    def update(
        self,
        profile: WorkerProfile,
        display_name: Optional[str] = None,
        bio: Optional[str] = None,
    ) -> WorkerProfile:
        if display_name is not None:
            profile.display_name = display_name
        if bio is not None:
            profile.bio = bio
        self.db.flush()
        return profile


class OrganizationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, org_id: UUID) -> Optional[Organization]:
        return self.db.get(Organization, org_id)

    def get_memberships_by_user(self, user_id: UUID) -> list[tuple[Organization, OrganizationMembership]]:
        return self.db.execute(
            select(Organization, OrganizationMembership)
            .join(OrganizationMembership, Organization.id == OrganizationMembership.organization_id)
            .where(OrganizationMembership.user_id == user_id)
        ).all()

    def create_with_owner(
        self, name: str, organization_type: str, owner_id: UUID
    ) -> tuple[Organization, OrganizationMembership]:
        org = Organization(name=name, organization_type=organization_type)
        self.db.add(org)
        self.db.flush()

        membership = OrganizationMembership(
            organization_id=org.id,
            user_id=owner_id,
            membership_role="owner",
        )
        self.db.add(membership)
        self.db.flush()

        return org, membership