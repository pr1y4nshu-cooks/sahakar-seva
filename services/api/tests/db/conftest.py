"""Isolated PostgreSQL fixtures for database integration tests.

- Uses TEST_DATABASE_URL only (validated by app.db.testing); never the development DB.
- Migrates the test database to Alembic head once per session.
- Each test runs inside an outer transaction that is always rolled back. Repository
  ``commit()`` calls only release a SAVEPOINT (join_transaction_mode="create_savepoint"),
  so no test data is ever durably written, even in the test database.
"""

from collections.abc import Generator
import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.testing import UnsafeTestDatabaseError, alembic_config, resolve_test_database_url
from app.main import app

@pytest.fixture(scope="session")
def test_database_url() -> str:
    try:
        return resolve_test_database_url()
    except UnsafeTestDatabaseError as exc:
        pytest.fail(f"Database tests not run: {exc}", pytrace=False)


@pytest.fixture(scope="session")
def test_engine(test_database_url: str) -> Generator[Engine, None, None]:
    engine = create_engine(test_database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        current = conn.execute(text("SELECT current_database()")).scalar_one()
    if "test" not in current.lower():  # defence in depth against DNS/alias tricks
        pytest.fail(f"Connected database '{current}' is not a test database.", pytrace=False)
    command.upgrade(alembic_config(test_database_url), "head")
    counts_before = _row_counts(engine)
    yield engine
    counts_after = _row_counts(engine)
    engine.dispose()
    leaked = {t: counts_after[t] - counts_before[t] for t in counts_before if counts_after[t] != counts_before[t]}
    if leaked:
        pytest.fail(f"Database tests leaked rows into the test database: {leaked}", pytrace=False)


_LEAK_CHECK_TABLES = (
    "users",
    "worker_profiles",
    "organizations",
    "organization_memberships",
    "service_categories",
    "skills",
    "worker_skills",
    "worker_service_settings",
    "availability_slots",
    "jobs",
    "job_applications",
    "bookings",
    "settlements",
    "disputes",
    "platform_reviewers",
    "audit_events",
)


def _row_counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in _LEAK_CHECK_TABLES}


@pytest.fixture
def db(test_engine: Engine) -> Generator[Session, None, None]:
    connection = test_engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    # Any API call made from a DB test uses the same isolated session.
    app.dependency_overrides[get_db] = lambda: (yield session)
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
