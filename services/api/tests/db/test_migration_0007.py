"""Migration 0007_demo_provenance: one additive table, clean downgrade, no effect on existing rows."""

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.db.testing import alembic_config
from test_migration_0003 import PHASE3A, _tables, _version, scratch  # noqa: F401

PREV, HEAD = "0006_configurable_fee_policies", "0007_demo_provenance"


def test_0007_follows_0006_and_is_head() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql+psycopg://unused/unused_test"))
    assert script.get_revision(HEAD).down_revision == PREV and script.get_heads() == [HEAD]


def test_upgrade_and_downgrade_are_clean(scratch) -> None:
    conn, cfg, schema = scratch
    command.upgrade(cfg, PHASE3A)
    conn.commit()
    conn.execute(text(f'SET search_path TO "{schema}", public'))
    command.upgrade(cfg, PREV)
    conn.commit()
    command.upgrade(cfg, HEAD)
    conn.commit()
    assert _version(conn) == HEAD and "demo_seed_records" in _tables(conn, schema)
    assert conn.execute(text("SELECT count(*) FROM demo_seed_records")).scalar_one() == 0
    command.downgrade(cfg, PREV)
    conn.commit()
    assert _version(conn) == PREV and "demo_seed_records" not in _tables(conn, schema)
