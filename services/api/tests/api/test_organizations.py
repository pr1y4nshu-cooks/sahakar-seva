from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import VerifiedUser, get_token_verifier
from app.main import app
from app.models.organization import Organization, OrganizationMembership
from app.services.organization_service import OrganizationService


def test_organization_creation_and_listing(client: TestClient) -> None:
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_org_user", email="org_user@example.com", display_name_hint="Org Owner"
    )
    headers = {"Authorization": "Bearer org_user"}

    try:
        # Initially empty list
        list_resp0 = client.get("/api/v1/organizations/mine", headers=headers)
        assert list_resp0.status_code == 200
        assert list_resp0.json() == []

        # 1. Create a business organization
        resp1 = client.post(
            "/api/v1/organizations",
            json={"name": "Zephyr Tech Co", "organization_type": "business"},
            headers=headers,
        )
        assert resp1.status_code == 201
        org1 = resp1.json()
        assert org1["name"] == "Zephyr Tech Co"
        assert org1["organization_type"] == "business"
        assert org1["my_membership_role"] == "owner"
        assert "id" in org1

        # 2. Create a cooperative organization
        resp2 = client.post(
            "/api/v1/organizations",
            json={"name": "Sahakar Cleaners Cooperative", "organization_type": "cooperative"},
            headers=headers,
        )
        assert resp2.status_code == 201
        org2 = resp2.json()
        assert org2["name"] == "Sahakar Cleaners Cooperative"
        assert org2["organization_type"] == "cooperative"
        assert org2["my_membership_role"] == "owner"

        # 3. List my organizations
        list_resp = client.get("/api/v1/organizations/mine", headers=headers)
        assert list_resp.status_code == 200
        orgs = list_resp.json()
        assert len(orgs) == 2
        org_names = [o["name"] for o in orgs]
        assert "Zephyr Tech Co" in org_names
        assert "Sahakar Cleaners Cooperative" in org_names
        for o in orgs:
            assert o["my_membership_role"] == "owner"

        # 4. Reject invalid organization_type
        bad_type_resp = client.post(
            "/api/v1/organizations",
            json={"name": "Invalid Org", "organization_type": "corporation"},
            headers=headers,
        )
        assert bad_type_resp.status_code == 422
        assert bad_type_resp.json()["error"]["code"] == "VALIDATION_ERROR"

        # 5. Reject short name (< 2 chars)
        short_name_resp = client.post(
            "/api/v1/organizations",
            json={"name": " ", "organization_type": "business"},
            headers=headers,
        )
        assert short_name_resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_organization_isolation_between_users(client: TestClient) -> None:
    # User A creates an organization
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_org_a", email="a@example.com", display_name_hint="User A"
    )
    resp_a = client.post(
        "/api/v1/organizations",
        json={"name": "User A Exclusive Org", "organization_type": "business"},
        headers={"Authorization": "Bearer a"},
    )
    assert resp_a.status_code == 201

    # User B lists organizations -> must NOT see User A's organization
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_org_b", email="b@example.com", display_name_hint="User B"
    )
    resp_b = client.get(
        "/api/v1/organizations/mine",
        headers={"Authorization": "Bearer b"},
    )
    assert resp_b.status_code == 200
    assert resp_b.json() == []
    app.dependency_overrides.clear()


def test_organization_transaction_atomicity(db_session: Session, monkeypatch) -> None:
    """
    Test that if membership creation fails during organization creation,
    the entire transaction is rolled back and neither the organization nor the
    membership row persists in the database.

    The failure is injected inside the canonical repository (the code path the
    service now delegates to), after the organization row has been flushed.
    """
    from uuid import uuid4

    import pytest

    from app.repositories import organization_repository

    test_user_id = uuid4()

    def failing_membership(*args, **kwargs):
        raise RuntimeError("Injected database error during membership creation")

    monkeypatch.setattr(organization_repository, "OrganizationMembership", failing_membership)

    with pytest.raises(RuntimeError):
        OrganizationService.create_organization_with_owner(
            db=db_session,
            user_id=test_user_id,
            name="Atomic Org",
            organization_type="business",
        )

    # Verify that the organization row was NOT committed
    org_in_db = db_session.scalar(select(Organization).where(Organization.name == "Atomic Org"))
    assert org_in_db is None

    # Verify that no membership row was committed
    mem_in_db = db_session.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == test_user_id))
    assert mem_in_db is None


def test_organization_api_failure_rolls_back_and_returns_contract_error(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    """API-level atomicity: injected membership failure -> 500 INTERNAL_ERROR, zero orgs persisted."""
    from app.repositories import organization_repository

    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_org_atomic_api", email="atomic_api@example.com", display_name_hint="Atomic"
    )
    headers = {"Authorization": "Bearer atomic"}
    try:
        # Sync the user first so only the organization insert is under test
        assert client.get("/api/v1/users/me", headers=headers).status_code == 200

        def failing_membership(*args, **kwargs):
            raise RuntimeError("simulated failure with secret-ish detail")

        monkeypatch.setattr(organization_repository, "OrganizationMembership", failing_membership)
        resp = client.post(
            "/api/v1/organizations",
            json={"name": "Never Persisted Org", "organization_type": "cooperative"},
            headers=headers,
        )
        assert resp.status_code == 500
        assert resp.json() == {
            "error": {"code": "INTERNAL_ERROR", "message": "An unexpected server error occurred."}
        }
        monkeypatch.undo()

        assert db_session.scalar(select(Organization).where(Organization.name == "Never Persisted Org")) is None
        listing = client.get("/api/v1/organizations/mine", headers=headers)
        assert listing.status_code == 200
        assert listing.json() == []
    finally:
        app.dependency_overrides.clear()
