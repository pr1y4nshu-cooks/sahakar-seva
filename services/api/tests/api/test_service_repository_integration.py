"""ARCH-01 regression tests: services delegate persistence to the canonical repositories
while preserving the Phase 2 API contract and security behaviour."""

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import VerifiedUser, get_token_verifier
from app.main import app
from app.models.organization import Organization, OrganizationMembership
from app.models.user import User, WorkerProfile
from app.repositories import organization_repository, user_repository, worker_repository


def _as(sub: str, email: str, name: str = "Test Person") -> dict[str, str]:
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub=sub, email=email, display_name_hint=name
    )
    return {"Authorization": f"Bearer {sub}"}


def _spy(monkeypatch, module, name: str, calls: list[str]) -> None:
    original = getattr(module, name)

    def wrapper(*args, **kwargs):
        calls.append(name)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)


def test_endpoints_delegate_to_canonical_repositories(client: TestClient, monkeypatch) -> None:
    calls: list[str] = []
    _spy(monkeypatch, user_repository, "get_or_create_user_from_verified_identity", calls)
    _spy(monkeypatch, user_repository, "update_own_user_display_name", calls)
    _spy(monkeypatch, worker_repository, "create_worker_profile_for_user", calls)
    _spy(monkeypatch, worker_repository, "get_worker_profile_by_user", calls)
    _spy(monkeypatch, worker_repository, "update_worker_profile_for_user", calls)
    _spy(monkeypatch, organization_repository, "create_organization_with_owner", calls)
    _spy(monkeypatch, organization_repository, "list_organizations_for_user", calls)

    headers = _as("sub_delegate", "delegate@example.com")
    try:
        assert client.get("/api/v1/users/me", headers=headers).status_code == 200
        assert client.patch("/api/v1/users/me", json={"display_name": "Delegated"}, headers=headers).status_code == 200
        assert client.post("/api/v1/worker-profiles", json={"display_name": "Delegate W"}, headers=headers).status_code == 201
        assert client.get("/api/v1/worker-profiles/me", headers=headers).status_code == 200
        assert client.patch("/api/v1/worker-profiles/me", json={"bio": "hi"}, headers=headers).status_code == 200
        assert client.post(
            "/api/v1/organizations", json={"name": "Delegate Org", "organization_type": "business"}, headers=headers
        ).status_code == 201
        assert client.get("/api/v1/organizations/mine", headers=headers).status_code == 200
    finally:
        app.dependency_overrides.clear()

    for name in (
        "get_or_create_user_from_verified_identity",
        "update_own_user_display_name",
        "create_worker_profile_for_user",
        "get_worker_profile_by_user",
        "update_worker_profile_for_user",
        "create_organization_with_owner",
        "list_organizations_for_user",
    ):
        assert name in calls, f"service layer did not call repository function {name}"


def test_response_shapes_match_contract(client: TestClient) -> None:
    headers = _as("sub_shape", "shape@example.com", "Shape User")
    try:
        user = client.get("/api/v1/users/me", headers=headers).json()
        assert set(user) == {"id", "display_name", "email", "created_at", "updated_at"}

        worker = client.post(
            "/api/v1/worker-profiles", json={"display_name": "Shape Worker", "bio": None}, headers=headers
        ).json()
        assert set(worker) == {"id", "user_id", "display_name", "bio", "onboarding_status", "created_at", "updated_at"}
        assert worker["user_id"] == user["id"]
        assert worker["onboarding_status"] == "draft"

        org = client.post(
            "/api/v1/organizations", json={"name": "Shape Co", "organization_type": "cooperative"}, headers=headers
        ).json()
        assert set(org) == {"id", "name", "organization_type", "my_membership_role", "created_at", "updated_at"}
        assert org["my_membership_role"] == "owner"
    finally:
        app.dependency_overrides.clear()


def test_repeated_sync_creates_exactly_one_user_row(client: TestClient, db_session: Session) -> None:
    headers = _as("sub_once", "once@example.com")
    try:
        ids = {client.get("/api/v1/users/me", headers=headers).json()["id"] for _ in range(3)}
        client.patch("/api/v1/users/me", json={"display_name": "Once Again"}, headers=headers)
    finally:
        app.dependency_overrides.clear()
    assert len(ids) == 1
    count = db_session.scalar(select(func.count()).select_from(User).where(User.external_auth_id == "sub_once"))
    assert count == 1


def test_identity_conflict_does_not_leak_email(client: TestClient, db_session: Session) -> None:
    db_session.add(User(external_auth_id="sub_owner", email="owner@example.com", display_name="Owner"))
    db_session.commit()
    headers = _as("sub_intruder", "owner@example.com", "Intruder")
    try:
        resp = client.get("/api/v1/users/me", headers=headers)
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "IDENTITY_CONFLICT"
    assert "owner@example.com" not in resp.text
    owner = db_session.scalar(select(User).where(User.email == "owner@example.com"))
    assert owner.external_auth_id == "sub_owner"


def test_duplicate_worker_profile_keeps_single_row(client: TestClient, db_session: Session) -> None:
    headers = _as("sub_dupw", "dupw@example.com")
    try:
        first = client.post("/api/v1/worker-profiles", json={"display_name": "First"}, headers=headers)
        second = client.post("/api/v1/worker-profiles", json={"display_name": "Second"}, headers=headers)
    finally:
        app.dependency_overrides.clear()
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "WORKER_PROFILE_EXISTS"
    user_id = UUID(first.json()["user_id"])
    rows = db_session.scalars(select(WorkerProfile).where(WorkerProfile.user_id == user_id)).all()
    assert len(rows) == 1
    assert rows[0].display_name == "First"


def test_worker_cannot_self_approve_or_change_owner(client: TestClient, db_session: Session) -> None:
    headers = _as("sub_selfapprove", "selfapprove@example.com")
    try:
        created = client.post("/api/v1/worker-profiles", json={"display_name": "Honest"}, headers=headers).json()
        for body in (
            {"display_name": "Sneaky", "onboarding_status": "approved"},
            {"user_id": "00000000-0000-0000-0000-000000000000"},
            {"is_admin": True},
        ):
            resp = client.patch("/api/v1/worker-profiles/me", json=body, headers=headers)
            assert resp.status_code == 422
            assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
        create_approved = client.post(
            "/api/v1/worker-profiles", json={"display_name": "X Y", "onboarding_status": "approved"}, headers=headers
        )
        assert create_approved.status_code == 422
        current = client.get("/api/v1/worker-profiles/me", headers=headers).json()
    finally:
        app.dependency_overrides.clear()
    assert current["onboarding_status"] == "draft"
    assert current["display_name"] == "Honest"
    assert current["user_id"] == created["user_id"]


def test_user_b_cannot_modify_user_a_worker_profile(client: TestClient) -> None:
    headers_a = _as("sub_iso_a", "iso_a@example.com")
    try:
        client.post("/api/v1/worker-profiles", json={"display_name": "Alpha", "bio": "A bio"}, headers=headers_a)
        headers_b = _as("sub_iso_b", "iso_b@example.com")
        # B has no profile: PATCH /me must 404 instead of touching A's row
        resp = client.patch("/api/v1/worker-profiles/me", json={"bio": "pwned"}, headers=headers_b)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        headers_a = _as("sub_iso_a", "iso_a@example.com")
        assert client.get("/api/v1/worker-profiles/me", headers=headers_a).json()["bio"] == "A bio"
    finally:
        app.dependency_overrides.clear()


def test_organization_creation_creates_exactly_one_owner_membership(
    client: TestClient, db_session: Session
) -> None:
    headers = _as("sub_org_once", "org_once@example.com")
    try:
        org = client.post(
            "/api/v1/organizations", json={"name": "One Owner Co", "organization_type": "business"}, headers=headers
        ).json()
        rejected = client.post(
            "/api/v1/organizations",
            json={"name": "Role Escalation", "organization_type": "business", "role": "admin"},
            headers=headers,
        )
    finally:
        app.dependency_overrides.clear()
    assert rejected.status_code == 422
    memberships = db_session.scalars(
        select(OrganizationMembership).where(OrganizationMembership.organization_id == UUID(org["id"]))
    ).all()
    assert len(memberships) == 1
    assert memberships[0].membership_role == "owner"
    assert db_session.scalar(select(func.count()).select_from(Organization).where(Organization.name == "Role Escalation")) == 0
