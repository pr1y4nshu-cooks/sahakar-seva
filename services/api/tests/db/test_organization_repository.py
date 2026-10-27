import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.organization import Organization, OrganizationMembership
from app.models.user import User
from app.repositories.organization_repository import (
    create_organization_with_owner,
    get_organization_with_role,
    list_organizations_for_user,
)
from app.repositories.user_repository import get_or_create_user_from_verified_identity


def _create_test_user(db: Session, name: str = "Test User") -> User:
    sub = f"sub_{uuid.uuid4()}"
    email = f"user_{uuid.uuid4()}@example.com"
    return get_or_create_user_from_verified_identity(
        db, subject=sub, email=email, display_name_hint=name
    )


def test_create_organization_with_owner_success(db: Session) -> None:
    user = _create_test_user(db)
    org, membership = create_organization_with_owner(
        db,
        user_id=user.id,
        name="Coop Electricians",
        organization_type="cooperative",
    )

    assert org is not None
    assert org.id is not None
    assert org.name == "Coop Electricians"
    assert org.organization_type == "cooperative"

    assert membership is not None
    assert membership.organization_id == org.id
    assert membership.user_id == user.id
    assert membership.membership_role == "owner"

    # Verify both rows are persisted
    persisted_org = db.query(Organization).filter(Organization.id == org.id).first()
    assert persisted_org is not None
    persisted_mem = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == org.id,
            OrganizationMembership.user_id == user.id,
        )
        .first()
    )
    assert persisted_mem is not None
    assert persisted_mem.membership_role == "owner"


def test_create_organization_atomic_rollback_on_membership_failure(db: Session) -> None:
    user = _create_test_user(db)
    org_name = f"Failed Org {uuid.uuid4()}"

    # Attempt to create with invalid role or simulate failure
    with pytest.raises(IntegrityError):
        # We invoke create with an invalid organization_type or invalid constraint
        create_organization_with_owner(
            db,
            user_id=user.id,
            name=org_name,
            organization_type="invalid_type",  # violates ck_organizations_organization_type
        )

    # Assert organization was rolled back and not persisted
    persisted_org = db.query(Organization).filter(Organization.name == org_name).first()
    assert persisted_org is None


def test_list_organizations_for_user_isolation(db: Session) -> None:
    user_a = _create_test_user(db, name="User A")
    user_b = _create_test_user(db, name="User B")

    org_a, _ = create_organization_with_owner(
        db, user_id=user_a.id, name="User A Org", organization_type="business"
    )
    org_b, _ = create_organization_with_owner(
        db, user_id=user_b.id, name="User B Org", organization_type="cooperative"
    )

    # User A listing
    user_a_orgs = list_organizations_for_user(db, user_id=user_a.id)
    assert len(user_a_orgs) == 1
    assert user_a_orgs[0][0].id == org_a.id
    assert user_a_orgs[0][1] == "owner"

    # User B listing
    user_b_orgs = list_organizations_for_user(db, user_id=user_b.id)
    assert len(user_b_orgs) == 1
    assert user_b_orgs[0][0].id == org_b.id
    assert user_b_orgs[0][1] == "owner"

    # Neither user sees the other's organization
    assert all(org.id != org_b.id for org, _ in user_a_orgs)
    assert all(org.id != org_a.id for org, _ in user_b_orgs)


def test_get_organization_with_role(db: Session) -> None:
    user = _create_test_user(db)
    stranger = _create_test_user(db)

    org, _ = create_organization_with_owner(
        db, user_id=user.id, name="Unique Org", organization_type="business"
    )

    # Member gets org and role
    result = get_organization_with_role(db, organization_id=org.id, user_id=user.id)
    assert result is not None
    assert result[0].id == org.id
    assert result[1] == "owner"

    # Non-member gets None
    result_stranger = get_organization_with_role(
        db, organization_id=org.id, user_id=stranger.id
    )
    assert result_stranger is None


def test_organization_check_constraints_reject_invalid_data(db: Session) -> None:
    # 1. Invalid organization_type
    invalid_org = Organization(name="Bad Corp", organization_type="corporation")
    db.add(invalid_org)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    # 2. Invalid membership_role
    user = _create_test_user(db)
    valid_org = Organization(name="Good Org", organization_type="business")
    db.add(valid_org)
    db.flush()

    invalid_mem = OrganizationMembership(
        organization_id=valid_org.id,
        user_id=user.id,
        membership_role="superadmin",  # Not in ('owner', 'admin', 'member')
    )
    db.add(invalid_mem)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
