"""Phase 3A Task A: database integration tests must be isolated from the development DB."""

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.db.testing import UnsafeTestDatabaseError, assert_safe_test_database_url
from app.models.user import User
from app.repositories.user_repository import get_or_create_user_from_verified_identity

DEV = "postgresql+psycopg://sahakar:sahakar@localhost:55432/sahakar_seva"
SAFE = "postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_seva_test"


def test_guard_rejects_missing_url() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="not set"):
        assert_safe_test_database_url(None, [DEV])


@pytest.mark.parametrize(
    "url",
    [
        DEV,  # identical to development
        "postgresql+psycopg://other:pw@127.0.0.1:55432/sahakar_seva",  # same target, other creds/host alias
        "postgresql+psycopg://sahakar:sahakar@localhost:55432/sahakar_dev",  # name lacks "test"
    ],
)
def test_guard_rejects_development_or_non_test_targets(url: str) -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        assert_safe_test_database_url(url, [DEV])


def test_guard_rejects_test_named_url_equal_to_protected_url() -> None:
    misconfigured_dev = "postgresql+psycopg://u:p@db:5432/app_test"
    with pytest.raises(UnsafeTestDatabaseError, match="same database"):
        assert_safe_test_database_url(misconfigured_dev, [misconfigured_dev])


def test_guard_rejects_non_postgres() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="PostgreSQL"):
        assert_safe_test_database_url("sqlite:///test.db", [DEV])


def test_guard_accepts_isolated_test_database() -> None:
    assert assert_safe_test_database_url(SAFE, [DEV]) == SAFE


def test_session_is_connected_to_configured_test_database(db: Session, test_database_url: str) -> None:
    current = db.execute(text("SELECT current_database()")).scalar_one()
    assert current == make_url(test_database_url).database
    assert "test" in current


def test_repository_commits_do_not_escape_the_test_transaction(db: Session, test_engine: Engine) -> None:
    """A repository commit inside a test must not be visible to any other connection."""
    user = get_or_create_user_from_verified_identity(
        db, subject="isolation-probe-sub", email="isolation-probe@isolation.test", display_name_hint="Probe"
    )
    assert db.get(User, user.id) is not None  # visible inside the test

    with test_engine.connect() as other:
        leaked = other.execute(
            text("SELECT count(*) FROM users WHERE email = 'isolation-probe@isolation.test'")
        ).scalar_one()
    assert leaked == 0
