from fastapi.testclient import TestClient

from app.core.security import VerifiedUser, get_token_verifier
from app.main import app


def test_get_users_me_idempotent_sync(client: TestClient) -> None:
    def fake_verifier(token: str) -> VerifiedUser:
        return VerifiedUser(sub="sub_bob", email="bob@example.com", display_name_hint="Bob Builder")

    app.dependency_overrides[get_token_verifier] = lambda: fake_verifier
    try:
        # First call creates the user
        resp1 = client.get("/api/v1/users/me", headers={"Authorization": "Bearer bob_token"})
        assert resp1.status_code == 200
        user1 = resp1.json()
        assert user1["display_name"] == "Bob Builder"
        assert user1["email"] == "bob@example.com"
        assert "id" in user1
        assert "created_at" in user1
        assert "updated_at" in user1

        # Second call returns the same user without creating a duplicate row
        resp2 = client.get("/api/v1/users/me", headers={"Authorization": "Bearer bob_token"})
        assert resp2.status_code == 200
        user2 = resp2.json()
        assert user1["id"] == user2["id"]
    finally:
        app.dependency_overrides.pop(get_token_verifier, None)


def test_users_isolation_two_different_subjects(client: TestClient) -> None:
    # User A
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_a", email="a@example.com", display_name_hint="User A"
    )
    resp_a = client.get("/api/v1/users/me", headers={"Authorization": "Bearer a"})
    assert resp_a.status_code == 200
    user_a = resp_a.json()

    # User B
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_b", email="b@example.com", display_name_hint="User B"
    )
    resp_b = client.get("/api/v1/users/me", headers={"Authorization": "Bearer b"})
    assert resp_b.status_code == 200
    user_b = resp_b.json()

    # Verify no cross-account profile leakage
    assert user_a["id"] != user_b["id"]
    assert user_a["email"] != user_b["email"]
    assert user_a["display_name"] == "User A"
    assert user_b["display_name"] == "User B"
    app.dependency_overrides.clear()


def test_patch_users_me_display_name_success(client: TestClient) -> None:
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_charlie", email="charlie@example.com", display_name_hint="Charlie Old"
    )
    try:
        resp = client.patch(
            "/api/v1/users/me",
            json={"display_name": "  Charlie New Name  "},
            headers={"Authorization": "Bearer charlie"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "Charlie New Name"
        assert data["email"] == "charlie@example.com"
    finally:
        app.dependency_overrides.clear()


def test_patch_users_me_rejects_empty_body(client: TestClient) -> None:
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_d", email="d@example.com", display_name_hint="User D"
    )
    try:
        resp = client.patch(
            "/api/v1/users/me",
            json={},
            headers={"Authorization": "Bearer d"},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()


def test_patch_users_me_rejects_forbidden_fields(client: TestClient) -> None:
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_e", email="e@example.com", display_name_hint="User E"
    )
    try:
        # Attempt to patch email or external_auth_id or is_admin
        resp = client.patch(
            "/api/v1/users/me",
            json={"display_name": "User E Valid", "email": "hacked@example.com", "is_admin": True},
            headers={"Authorization": "Bearer e"},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()


def test_patch_users_me_length_constraints(client: TestClient) -> None:
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_f", email="f@example.com", display_name_hint="User F"
    )
    try:
        # Too short (< 2)
        resp1 = client.patch(
            "/api/v1/users/me",
            json={"display_name": "A"},
            headers={"Authorization": "Bearer f"},
        )
        assert resp1.status_code == 422

        # Too long (> 80)
        resp2 = client.patch(
            "/api/v1/users/me",
            json={"display_name": "X" * 81},
            headers={"Authorization": "Bearer f"},
        )
        assert resp2.status_code == 422
    finally:
        app.dependency_overrides.clear()
