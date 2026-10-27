from fastapi.testclient import TestClient

from app.core.security import VerifiedUser, get_token_verifier
from app.main import app


def test_worker_profile_flow_and_constraints(client: TestClient) -> None:
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_worker_1", email="worker1@example.com", display_name_hint="Worker One"
    )
    headers = {"Authorization": "Bearer worker1"}

    try:
        # 1. GET before creation -> 404
        get_resp = client.get("/api/v1/worker-profiles/me", headers=headers)
        assert get_resp.status_code == 404
        assert get_resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

        # 2. POST worker profile -> 201 with onboarding_status="draft"
        create_resp = client.post(
            "/api/v1/worker-profiles",
            json={"display_name": "Worker Pro", "bio": "Plumbing and electrical expert."},
            headers=headers,
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created["display_name"] == "Worker Pro"
        assert created["bio"] == "Plumbing and electrical expert."
        assert created["onboarding_status"] == "draft"
        assert "id" in created
        assert "user_id" in created

        # 3. Duplicate POST for same user -> 409
        dup_resp = client.post(
            "/api/v1/worker-profiles",
            json={"display_name": "Worker Duplicate"},
            headers=headers,
        )
        assert dup_resp.status_code == 409
        assert dup_resp.json()["error"]["code"] == "WORKER_PROFILE_EXISTS"

        # 4. GET worker-profiles/me -> 200
        get_resp2 = client.get("/api/v1/worker-profiles/me", headers=headers)
        assert get_resp2.status_code == 200
        assert get_resp2.json()["id"] == created["id"]

        # 5. PATCH display_name
        patch_resp1 = client.patch(
            "/api/v1/worker-profiles/me",
            json={"display_name": "Worker Master"},
            headers=headers,
        )
        assert patch_resp1.status_code == 200
        assert patch_resp1.json()["display_name"] == "Worker Master"
        assert patch_resp1.json()["bio"] == "Plumbing and electrical expert."

        # 6. PATCH bio to null (clears bio)
        patch_resp2 = client.patch(
            "/api/v1/worker-profiles/me",
            json={"bio": None},
            headers=headers,
        )
        assert patch_resp2.status_code == 200
        assert patch_resp2.json()["bio"] is None

        # 7. Empty PATCH -> 422
        patch_empty = client.patch(
            "/api/v1/worker-profiles/me",
            json={},
            headers=headers,
        )
        assert patch_empty.status_code == 422
        assert patch_empty.json()["error"]["code"] == "VALIDATION_ERROR"

        # 8. Forbidden field rejection: trying to self-approve status
        patch_status = client.patch(
            "/api/v1/worker-profiles/me",
            json={"onboarding_status": "approved"},
            headers=headers,
        )
        assert patch_status.status_code == 422
        assert patch_status.json()["error"]["code"] == "VALIDATION_ERROR"

        # 9. Bio exceeding 500 chars -> 422
        patch_long_bio = client.patch(
            "/api/v1/worker-profiles/me",
            json={"bio": "X" * 501},
            headers=headers,
        )
        assert patch_long_bio.status_code == 422
        assert patch_long_bio.json()["error"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()


def test_worker_profile_isolation(client: TestClient) -> None:
    # User 1 creates worker profile
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_w_u1", email="u1@example.com", display_name_hint="User 1"
    )
    resp1 = client.post(
        "/api/v1/worker-profiles",
        json={"display_name": "User 1 Worker"},
        headers={"Authorization": "Bearer u1"},
    )
    assert resp1.status_code == 201

    # User 2 checks own profile -> 404 (does not see User 1's profile)
    app.dependency_overrides[get_token_verifier] = lambda: lambda t: VerifiedUser(
        sub="sub_w_u2", email="u2@example.com", display_name_hint="User 2"
    )
    resp2 = client.get(
        "/api/v1/worker-profiles/me",
        headers={"Authorization": "Bearer u2"},
    )
    assert resp2.status_code == 404
    app.dependency_overrides.clear()
