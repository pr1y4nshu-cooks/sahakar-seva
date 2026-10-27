from uuid import UUID

from sqlalchemy.orm import Session

from app.models.organization import Organization, OrganizationMembership


def create_organization_with_owner(
    db: Session,
    user_id: UUID,
    name: str,
    organization_type: str,
) -> tuple[Organization, OrganizationMembership]:
    """Atomically creates an organization and the creator's owner membership.

    Ensures that if creating the membership fails, the organization is rolled back
    and neither record is persisted.
    """
    clean_name = name.strip()
    clean_type = organization_type.strip()

    org = Organization(name=clean_name, organization_type=clean_type)

    try:
        with db.begin_nested():
            db.add(org)
            db.flush()

            membership = OrganizationMembership(
                organization_id=org.id,
                user_id=user_id,
                membership_role="owner",
            )
            db.add(membership)
            db.flush()

        db.commit()
        db.refresh(org)
        db.refresh(membership)
        return org, membership
    except Exception:
        db.rollback()
        raise


def list_organizations_for_user(
    db: Session,
    user_id: UUID,
) -> list[tuple[Organization, str]]:
    """Lists organizations where user_id has an active membership, returning tuples of

    (Organization, membership_role).
    Organizations where the caller is not a member are strictly excluded.
    """
    results = (
        db.query(Organization, OrganizationMembership.membership_role)
        .join(
            OrganizationMembership,
            Organization.id == OrganizationMembership.organization_id,
        )
        .filter(OrganizationMembership.user_id == user_id)
        .order_by(Organization.created_at.desc())
        .all()
    )
    return [(row[0], row[1]) for row in results]


def get_organization_with_role(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
) -> tuple[Organization, str] | None:
    """Retrieves an organization with caller's scoped membership role.

    Returns None if the organization does not exist or caller is not a member.
    """
    row = (
        db.query(Organization, OrganizationMembership.membership_role)
        .join(
            OrganizationMembership,
            Organization.id == OrganizationMembership.organization_id,
        )
        .filter(
            Organization.id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
        .first()
    )
    if not row:
        return None
    return row[0], row[1]
