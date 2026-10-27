"""Phase 3A Task C: migration 0003_skills_and_categories.

Runs in a throwaway schema inside the isolated test database so that fresh-install,
upgrade-from-Phase-2 (with existing rows) and downgrade paths are all exercised without
touching the shared test schema or any development data. PostGIS is already installed in
``public``, so migration 0001's ``CREATE EXTENSION IF NOT EXISTS postgis`` is a no-op here.
"""

import uuid
from collections.abc import Generator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.testing import alembic_config

PHASE2 = "0002_phase2_constraints"
PHASE3A = "0003_skills_and_categories"
NEW_TABLES = {"service_categories", "skills", "worker_skills"}


@pytest.fixture
def scratch(test_engine: Engine, test_database_url: str) -> Generator[tuple[Connection, object, str], None, None]:
    # Dedicated unpooled engine: the session-level search_path must never leak to pooled connections.
    engine = create_engine(test_database_url, poolclass=NullPool)
    schema = f"mig_{uuid.uuid4().hex[:10]}"
    conn = engine.connect()
    conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    # Only the scratch schema: with public on the path Alembic would find public.alembic_version.
    conn.execute(text(f'SET search_path TO "{schema}"'))
    conn.commit()
    cfg = alembic_config(test_database_url)
    cfg.attributes["connection"] = conn
    try:
        yield conn, cfg, schema
    finally:
        conn.rollback()
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        conn.commit()
        conn.close()
        engine.dispose()


def _tables(conn: Connection, schema: str) -> set[str]:
    return set(inspect(conn).get_table_names(schema=schema))


def _version(conn: Connection) -> str:
    return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def test_migration_graph_is_linear_with_expected_head() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql+psycopg://unused/unused_test"))
    assert script.get_heads() == [PHASE3A]
    assert script.get_revision(PHASE3A).down_revision == PHASE2


def test_fresh_database_upgrades_to_head(scratch) -> None:
    conn, cfg, schema = scratch
    command.upgrade(cfg, "head")
    conn.commit()
    assert _version(conn) == PHASE3A
    assert NEW_TABLES | {"users", "worker_profiles", "organizations", "organization_memberships"} <= _tables(conn, schema)


def test_upgrade_from_phase2_preserves_existing_rows_and_downgrade_is_clean(scratch) -> None:
    conn, cfg, schema = scratch
    command.upgrade(cfg, PHASE2)
    user_id, profile_id, org_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    conn.execute(
        text("INSERT INTO users (id, external_auth_id, display_name, email) VALUES (:id, 'sub-mig', 'Mig User', 'mig@migration.test')"),
        {"id": user_id},
    )
    conn.execute(
        text("INSERT INTO worker_profiles (id, user_id, display_name) VALUES (:id, :uid, 'Mig Worker')"),
        {"id": profile_id, "uid": user_id},
    )
    conn.execute(text("INSERT INTO organizations (id, name, organization_type) VALUES (:id, 'Mig Coop', 'cooperative')"), {"id": org_id})
    conn.execute(
        text("INSERT INTO organization_memberships (id, organization_id, user_id, membership_role) VALUES (:id, :o, :u, 'owner')"),
        {"id": uuid.uuid4(), "o": org_id, "u": user_id},
    )
    conn.commit()
    assert not (NEW_TABLES & _tables(conn, schema))

    command.upgrade(cfg, "head")
    conn.commit()
    assert _version(conn) == PHASE3A
    assert NEW_TABLES <= _tables(conn, schema)
    status = conn.execute(text("SELECT onboarding_status FROM worker_profiles WHERE id = :id"), {"id": profile_id}).scalar_one()
    assert status == "draft"
    counts = conn.execute(
        text("SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM worker_profiles), "
             "(SELECT count(*) FROM organizations), (SELECT count(*) FROM organization_memberships)")
    ).one()
    assert tuple(counts) == (1, 1, 1, 1)

    command.downgrade(cfg, PHASE2)
    conn.commit()
    assert _version(conn) == PHASE2
    assert not (NEW_TABLES & _tables(conn, schema))
    assert conn.execute(text("SELECT count(*) FROM worker_profiles")).scalar_one() == 1

    command.upgrade(cfg, "head")  # re-upgrade after downgrade is repeatable
    conn.commit()
    assert _version(conn) == PHASE3A


def test_models_match_migrated_schema(test_engine: Engine) -> None:
    """Autogenerate diff between SQLAlchemy models and the migrated test DB must be empty."""
    with test_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    # Only extension-owned tables (PostGIS spatial_ref_sys) may exist outside the app metadata.
    unexpected = [d for d in diff if not (isinstance(d, tuple) and d[0] == "remove_table")]
    assert unexpected == []
    extra_tables = {d[1].name for d in diff if isinstance(d, tuple) and d[0] == "remove_table"}
    assert extra_tables <= {"spatial_ref_sys"}


def test_phase3a_constraints_exist(test_engine: Engine) -> None:
    with test_engine.connect() as conn:
        names = set(
            conn.execute(
                text("SELECT conname FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
                     "WHERE n.nspname = 'public'")
            ).scalars()
        ) | set(conn.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")).scalars())
    expected = {
        "uq_service_categories_slug",
        "uq_service_categories_name_lower",
        "ck_service_categories_slug_format",
        "ck_service_categories_name_not_blank",
        "uq_skills_slug",
        "uq_skills_category_name_lower",
        "ck_skills_slug_format",
        "ck_skills_name_not_blank",
        "ix_skills_category_id",
        "skills_category_id_fkey",
        "uq_worker_skills_worker_profile_skill",
        "ix_worker_skills_skill_id",
        "worker_skills_worker_profile_id_fkey",
        "worker_skills_skill_id_fkey",
    }
    assert expected <= names, expected - names
