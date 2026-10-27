import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def database_url() -> str:
    """Isolated test database URL only; never falls back to the development DATABASE_URL."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.fail("TEST_DATABASE_URL is not set; refusing to fall back to the development database.", pytrace=False)
    return url
