"""Safety guard for database integration tests (Phase 3A, Task A).

Integration tests must run only against an explicitly configured, isolated test database.
This module refuses any TEST_DATABASE_URL that could point at the development or
production database.
"""

import os
from pathlib import Path

from sqlalchemy.engine import make_url

TEST_DATABASE_ENV = "TEST_DATABASE_URL"
DEFAULT_LOCAL_HINT = "postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_seva_test"


class UnsafeTestDatabaseError(RuntimeError):
    """Raised when the configured test database is missing or not provably isolated."""


def _target(url: str) -> tuple[str, int, str]:
    parsed = make_url(url)
    host = (parsed.host or "localhost").lower()
    if host in {"127.0.0.1", "::1"}:
        host = "localhost"
    return host, int(parsed.port or 5432), (parsed.database or "").lower()


def assert_safe_test_database_url(test_url: str | None, protected_urls: list[str | None]) -> str:
    """Return ``test_url`` if it is safe to use for destructive tests, else raise.

    Rules:
    - must be set explicitly;
    - must be PostgreSQL (constraints/PostGIS behaviour must match production);
    - database name must contain "test";
    - must not target the same host/port/database as any protected (dev/prod) URL.
    """
    if not test_url:
        raise UnsafeTestDatabaseError(
            f"{TEST_DATABASE_ENV} is not set. Database integration tests never fall back to the "
            f"development database. Create the isolated DB with "
            f"`sh services/api/scripts/create_test_database.sh` and export, e.g.\n"
            f"  {TEST_DATABASE_ENV}={DEFAULT_LOCAL_HINT}"
        )

    parsed = make_url(test_url)
    if not parsed.drivername.startswith("postgresql"):
        raise UnsafeTestDatabaseError(f"{TEST_DATABASE_ENV} must be a PostgreSQL URL, got '{parsed.drivername}'.")

    target = _target(test_url)
    if "test" not in target[2]:
        raise UnsafeTestDatabaseError(
            f"Refusing to use database '{target[2]}': test database names must contain 'test'."
        )

    for protected in protected_urls:
        if protected and _target(protected) == target:
            raise UnsafeTestDatabaseError(
                f"Refusing to run: {TEST_DATABASE_ENV} targets the same database as a protected "
                f"(development/production) URL ({target[0]}:{target[1]}/{target[2]})."
            )
    return test_url


def resolve_test_database_url() -> str:
    """Read TEST_DATABASE_URL and validate it against DATABASE_URL and the app default."""
    from app.core.config import Settings

    protected = [os.getenv("DATABASE_URL"), Settings.model_fields["database_url"].default]
    try:
        protected.append(Settings().database_url)  # includes a value from .env if present
    except Exception:  # pragma: no cover - misconfigured settings must not unlock tests
        pass
    if os.getenv("APP_ENV", "").lower() == "production":
        raise UnsafeTestDatabaseError("Refusing to run database tests with APP_ENV=production.")
    return assert_safe_test_database_url(os.getenv(TEST_DATABASE_ENV), protected)


API_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(url: str):
    """Alembic Config bound to an explicit URL (env.py will not override it with DATABASE_URL)."""
    from alembic.config import Config

    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.attributes["explicit_url"] = True
    return config
