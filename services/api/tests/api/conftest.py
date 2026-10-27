from collections.abc import Generator
from typing import Callable
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import (
    AuthProviderUnavailableException,
    InvalidTokenException,
    VerifiedUser,
    get_token_verifier,
)
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture(scope="session")
def test_engine():
    """Create in-memory SQLite database supporting multi-threaded tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    """Provide a clean transactional session for each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with database session dependency overridden."""
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_verified_user() -> Callable[..., VerifiedUser]:
    """Helper to construct VerifiedUser fixtures."""
    def _maker(
        sub: str | None = None,
        email: str | None = None,
        display_name: str | None = None,
    ) -> VerifiedUser:
        return VerifiedUser(
            sub=sub or f"sub_{uuid4().hex[:12]}",
            email=email or f"user_{uuid4().hex[:8]}@example.com",
            display_name_hint=display_name or "Test User",
        )
    return _maker


@pytest.fixture
def auth_headers_for():
    """Helper to generate bearer headers for a given subject."""
    def _headers(token: str = "valid_token") -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}
    return _headers
