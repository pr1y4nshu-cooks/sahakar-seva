"""Migration 0006_configurable_fee_policies: additive over 0005 data, constraint changes only widen value sets."""

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db.testing import alembic_config
from test_migration_0003 import PHASE3A, _tables, _version, scratch  # noqa: F401

PREV, HEAD = "0005_transparency_and_trust", "0006_configurable_fee_policies"


def test_0006_follows_0005() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql+psycopg://unused/unused_test"))
    assert script.get_revision(HEAD).down_revision == PREV  # head moved on to 0007 (see test_migration_0007.py)


def test_upgrade_and_downgrade_are_clean(scratch) -> None:
    conn, cfg, schema = scratch
    command.upgrade(cfg, PHASE3A)
    conn.commit()
    conn.execute(text(f'SET search_path TO "{schema}", public'))
    command.upgrade(cfg, PREV)
    conn.commit()
    command.upgrade(cfg, HEAD)  # 0006 specifically
    conn.commit()
    assert _version(conn) == HEAD and "fee_policies" in _tables(conn, schema)
    assert conn.execute(text("SELECT count(*) FROM fee_policies")).scalar_one() == 0  # nothing invented
    command.downgrade(cfg, PREV)
    conn.commit()
    assert _version(conn) == PREV and "fee_policies" not in _tables(conn, schema)


def test_safety_ceilings_still_in_place(test_engine: Engine) -> None:
    with test_engine.connect() as conn:
        defs = dict(conn.execute(text(
            "SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace "
            "WHERE n.nspname='public'")).all())
    for name in ("ck_bookings_fee_ceiling", "ck_settlements_fee_ceiling", "ck_price_quote_versions_fee_ceiling", "ck_fee_policies_charge_ceiling"):
        assert "2000" in defs[name], name
    assert "fee_paise + payout_paise" in defs["ck_bookings_fee_reconciles"]
    assert "worker_share_paise + platform_fee_paise" in defs["ck_price_quote_versions_allocation_reconciles"]
    for acct in ("simulated_customer_payment_clearing", "simulated_business_payment_clearing", "simulated_platform_promotion_expense"):
        assert acct in defs["ck_financial_ledger_entries_account"]
