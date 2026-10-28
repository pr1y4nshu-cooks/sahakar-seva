import uuid
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.organization import Organization, OrganizationMembership
from app.models.user import User, WorkerProfile


def test_postgis_extension_active(db: Session) -> None:
    result = db.execute(text("SELECT PostGIS_Version()")).scalar()
    assert result is not None
    assert "3.4" in str(result) or "3." in str(result)


def test_alembic_head_revision(db: Session) -> None:
    current_rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert current_rev == "0007_demo_provenance"


def test_db_enforces_external_auth_id_uniqueness(db: Session) -> None:
    shared_sub = f"sub_{uuid.uuid4()}"
    u1 = User(
        external_auth_id=shared_sub,
        email=f"u1_{uuid.uuid4()}@example.com",
        display_name="User 1",
    )
    u2 = User(
        external_auth_id=shared_sub,
        email=f"u2_{uuid.uuid4()}@example.com",
        display_name="User 2",
    )
    db.add(u1)
    db.flush()

    db.add(u2)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_db_enforces_worker_profile_user_id_uniqueness(db: Session) -> None:
    u = User(
        external_auth_id=f"sub_{uuid.uuid4()}",
        email=f"u_{uuid.uuid4()}@example.com",
        display_name="Worker User",
    )
    db.add(u)
    db.flush()

    wp1 = WorkerProfile(user_id=u.id, display_name="Worker 1")
    wp2 = WorkerProfile(user_id=u.id, display_name="Worker 2")
    db.add(wp1)
    db.flush()

    db.add(wp2)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_db_enforces_organization_membership_pair_uniqueness(db: Session) -> None:
    u = User(
        external_auth_id=f"sub_{uuid.uuid4()}",
        email=f"u_{uuid.uuid4()}@example.com",
        display_name="Org User",
    )
    org = Organization(name="Test Org", organization_type="business")
    db.add_all([u, org])
    db.flush()

    mem1 = OrganizationMembership(
        organization_id=org.id, user_id=u.id, membership_role="owner"
    )
    mem2 = OrganizationMembership(
        organization_id=org.id, user_id=u.id, membership_role="member"
    )
    db.add(mem1)
    db.flush()

    db.add(mem2)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_database_health_down_returns_503() -> None:
    def broken_get_db():
        mock_session = MagicMock()
        mock_session.execute.side_effect = SQLAlchemyError("Database connection failed")
        yield mock_session

    app.dependency_overrides[get_db] = broken_get_db
    try:
        client = TestClient(app)
        response = client.get("/api/v1/health/db")
        assert response.status_code == 503
        assert response.json()["detail"] == {"status": "error", "database": "unavailable"}
    finally:
        app.dependency_overrides.pop(get_db, None)
