"""Migration 0005_transparency_and_trust: additive over existing marketplace data, clean downgrade."""

import uuid
from datetime import datetime, timedelta, timezone

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db.testing import alembic_config
from test_migration_0003 import PHASE3A, _tables, _version, scratch  # noqa: F401

PREV = "0004_marketplace_core"
HEAD = "0005_transparency_and_trust"
NEW = {"financial_events", "price_quote_versions", "quote_acceptances", "financial_ledger_transactions",
       "financial_ledger_entries", "anchor_checkpoints"}


def test_0005_follows_0004() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql+psycopg://unused/unused_test"))
    assert script.get_revision(HEAD).down_revision == PREV


def _seed_0004(conn) -> dict:
    ids = {k: uuid.uuid4() for k in ("u", "c", "wp", "cat", "skill", "slot", "b", "s")}
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=3)
    conn.execute(text("INSERT INTO users (id, display_name, email) VALUES (:u, 'W', 'w@m5.test'), (:c, 'C', 'c@m5.test')"), ids)
    conn.execute(text("INSERT INTO worker_profiles (id, user_id, display_name) VALUES (:wp, :u, 'Keep Worker')"), ids)
    conn.execute(text("INSERT INTO service_categories (id, slug, name) VALUES (:cat, 'm5-cat', 'M5')"), ids)
    conn.execute(text("INSERT INTO skills (id, category_id, slug, name) VALUES (:skill, :cat, 'm5-skill', 'M5 skill')"), ids)
    conn.execute(text("INSERT INTO availability_slots (id, worker_profile_id, starts_at, ends_at) VALUES (:slot, :wp, :s0, :s1)"),
                 {**ids, "s0": start, "s1": start + timedelta(hours=2)})
    conn.execute(text(
        "INSERT INTO bookings (id, customer_user_id, worker_profile_id, origin, slot_id, skill_id, starts_at, ends_at, locality, "
        "address_details, price_paise, fee_bps, fee_paise, payout_paise, status) VALUES (:b, :c, :wp, 'direct', :slot, :skill, :s0, :s1, "
        "'Koramangala', 'addr', 70000, 1000, 7000, 63000, 'completed')"), {**ids, "s0": start, "s1": start + timedelta(hours=2)})
    conn.execute(text("INSERT INTO settlements (id, booking_id, gross_paise, fee_bps, fee_paise, payout_paise) VALUES (:s, :b, 70000, 1000, 7000, 63000)"), ids)
    return ids


def test_upgrade_preserves_legacy_bookings_and_settlements_and_downgrades_cleanly(scratch) -> None:
    conn, cfg, schema = scratch
    command.upgrade(cfg, PHASE3A)  # scratch schema only, so its own alembic_version is created and used
    conn.commit()
    # PostGIS/btree_gist live in public; the scratch schema stays first (same pattern as test_migration_0004).
    conn.execute(text(f'SET search_path TO "{schema}", public'))
    command.upgrade(cfg, PREV)
    conn.commit()
    assert _version(conn) == PREV and "bookings" in _tables(conn, schema)
    ids = _seed_0004(conn)
    conn.commit()
    command.upgrade(cfg, HEAD)  # this revision specifically; 0006 has its own test
    conn.commit()
    assert _version(conn) == HEAD and NEW <= _tables(conn, schema)
    row = conn.execute(text("SELECT price_paise, fee_paise, payout_paise, status, repeat_of_booking_id FROM bookings WHERE id = :b"), ids).one()
    assert tuple(row) == (70000, 7000, 63000, "completed", None)
    assert conn.execute(text("SELECT gross_paise FROM settlements WHERE id = :s"), ids).scalar_one() == 70000
    # No backfill: nothing is claimed for the historical booking.
    for table in NEW:
        assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
    command.downgrade(cfg, PREV)
    conn.commit()
    assert _version(conn) == PREV and not (NEW & _tables(conn, schema))
    assert conn.execute(text("SELECT count(*) FROM bookings")).scalar_one() == 1
    assert conn.execute(text("SELECT count(*) FROM settlements")).scalar_one() == 1


def test_0005_protections_exist(test_engine: Engine) -> None:
    with test_engine.connect() as conn:
        triggers = set(conn.execute(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")).scalars())
        deferred = dict(conn.execute(text(
            "SELECT tgname, tginitdeferred FROM pg_trigger WHERE tgname LIKE 'trg_financial_ledger_%_balanced'")).all())
        constraints = set(conn.execute(text(
            "SELECT conname FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='public'")).scalars())
    for t in ("financial_events", "price_quote_versions", "quote_acceptances", "financial_ledger_transactions", "financial_ledger_entries"):
        assert {f"trg_{t}_append_only", f"trg_{t}_no_truncate"} <= triggers
    assert {"trg_anchor_checkpoints_guard", "trg_bookings_price_guard", "trg_settlements_immutable"} <= triggers
    assert deferred == {"trg_financial_ledger_transactions_balanced": True, "trg_financial_ledger_entries_balanced": True}
    assert {
        "uq_financial_events_sequence", "uq_financial_events_previous_hash", "uq_financial_ledger_transactions_idempotency_key",
        "uq_financial_ledger_transactions_settlement_id", "ck_price_quote_versions_allocation_reconciles",
        "ck_price_quote_versions_fee_ceiling", "ck_anchor_checkpoints_anchored_evidence", "uq_settlements_booking_id",
    } <= constraints
