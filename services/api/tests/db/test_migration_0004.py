"""Migration 0004_marketplace_core: additive upgrade over existing data, clean downgrade, constraints."""

import uuid

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.db.testing import alembic_config
from test_migration_0003 import PHASE3A, _tables, _version, scratch  # noqa: F401

HEAD = "0004_marketplace_core"
NEW = {"worker_service_settings", "availability_slots", "jobs", "job_applications", "bookings",
       "settlements", "disputes", "platform_reviewers", "audit_events"}


def test_0004_follows_0003() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql+psycopg://unused/unused_test"))
    assert script.get_revision(HEAD).down_revision == PHASE3A


def test_upgrade_from_3a_preserves_rows_and_downgrades_cleanly(scratch) -> None:
    conn, cfg, schema = scratch
    command.upgrade(cfg, PHASE3A)
    uid, wid = uuid.uuid4(), uuid.uuid4()
    conn.execute(text("INSERT INTO users (id, display_name, email) VALUES (:id, 'Keep Me', 'keep@migration.test')"), {"id": uid})
    conn.execute(text("INSERT INTO worker_profiles (id, user_id, display_name) VALUES (:id, :u, 'Keep Worker')"), {"id": wid, "u": uid})
    conn.commit()
    # PostGIS types live in public; the scratch schema stays first so its alembic_version is used.
    conn.execute(text(f'SET search_path TO "{schema}", public'))
    command.upgrade(cfg, "head")
    conn.commit()
    assert _version(conn) == HEAD
    assert NEW <= _tables(conn, schema)
    assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
    assert conn.execute(text("SELECT display_name FROM worker_profiles")).scalar_one() == "Keep Worker"

    command.downgrade(cfg, PHASE3A)
    conn.commit()
    assert _version(conn) == PHASE3A
    assert not (NEW & _tables(conn, schema))
    assert conn.execute(text("SELECT count(*) FROM worker_profiles")).scalar_one() == 1


def test_0004_postgis_and_safety_constraints_exist(test_engine: Engine) -> None:
    with test_engine.connect() as conn:
        types = {
            r.column_name: r.udt_name
            for r in conn.execute(text(
                "SELECT column_name, udt_name FROM information_schema.columns "
                "WHERE table_schema='public' AND column_name IN ('service_point', 'job_point')"))
        }
        constraints = set(conn.execute(text(
            "SELECT conname FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='public'")).scalars())
        index_defs = dict(conn.execute(text(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public'")).all())
        triggers = set(conn.execute(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")).scalars())
        srid = conn.execute(text(
            "SELECT srid FROM geography_columns WHERE f_table_name='worker_service_settings'")).scalar_one()
    assert types == {"service_point": "geography", "job_point": "geography"}
    assert srid == 4326
    assert {"ex_bookings_worker_no_overlap", "ex_availability_slots_no_overlap", "uq_settlements_booking_id",
            "uq_job_applications_job_worker", "ck_bookings_fee_reconciles", "ck_settlements_simulated_only",
            "ck_disputes_not_self_reviewed"} <= constraints
    assert "USING gist" in index_defs["ix_worker_service_settings_point"]
    assert "USING gist" in index_defs["ix_jobs_point"]
    assert "WHERE" in index_defs["uq_bookings_active_job"]
    assert "trg_settlements_immutable" in triggers
    assert inspect is not None
