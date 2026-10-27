from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}


def test_database_health(client: TestClient) -> None:
    response = client.get("/api/v1/health/db")
    assert response.status_code in {200, 503}
    if response.status_code == 200:
        assert response.json() == {"status": "ok", "database": "connected"}
    else:
        assert response.json()["detail"] == {"status": "error", "database": "unavailable"}

