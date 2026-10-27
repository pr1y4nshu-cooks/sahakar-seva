import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def database_url() -> str:
    return os.getenv("TEST_DATABASE_URL", os.getenv("DATABASE_URL", "postgresql+psycopg://sahakar:sahakar@localhost:55432/sahakar_seva"))
