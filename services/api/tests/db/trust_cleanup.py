"""Test-only cleanup for tests that must COMMIT rows into the isolated test database.

Trust tables are append-only (triggers). Tests that commit real rows remove them afterwards by disabling
the append-only triggers *inside one transaction* on the isolated test database (the test role owns the
tables), deleting exactly the rows they created, and re-enabling the triggers before commit. This is never
used against the development database.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

APPEND_ONLY = (
    "financial_events", "price_quote_versions", "quote_acceptances",
    "financial_ledger_transactions", "financial_ledger_entries",
)


def purge_events(conn: Connection, event_ids: list) -> None:
    """Delete specific (booking-less) events committed by a test."""
    db_name = conn.execute(text("SELECT current_database()")).scalar_one()
    assert "test" in db_name.lower()
    conn.execute(text("ALTER TABLE financial_events DISABLE TRIGGER trg_financial_events_append_only"))
    try:
        conn.execute(text("DELETE FROM financial_events WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": [str(i) for i in event_ids]})
    finally:
        conn.execute(text("ALTER TABLE financial_events ENABLE TRIGGER trg_financial_events_append_only"))


def purge_trust_rows(conn: Connection, booking_ids: list) -> None:
    db_name = conn.execute(text("SELECT current_database()")).scalar_one()
    assert "test" in db_name.lower(), "purge_trust_rows is only for the isolated test database"
    for t in APPEND_ONLY:
        conn.execute(text(f"ALTER TABLE {t} DISABLE TRIGGER trg_{t}_append_only"))
    conn.execute(text("ALTER TABLE anchor_checkpoints DISABLE TRIGGER trg_anchor_checkpoints_guard"))
    conn.execute(text("ALTER TABLE settlements DISABLE TRIGGER trg_settlements_immutable"))
    try:
        ids = {"ids": [str(b) for b in booking_ids]}
        conn.execute(text("DELETE FROM financial_ledger_entries WHERE transaction_id IN "
                          "(SELECT id FROM financial_ledger_transactions WHERE booking_id = ANY(CAST(:ids AS uuid[])))"), ids)
        conn.execute(text("DELETE FROM financial_ledger_transactions WHERE booking_id = ANY(CAST(:ids AS uuid[]))"), ids)
        conn.execute(text("DELETE FROM quote_acceptances WHERE booking_id = ANY(CAST(:ids AS uuid[]))"), ids)
        conn.execute(text("DELETE FROM price_quote_versions WHERE booking_id = ANY(CAST(:ids AS uuid[]))"), ids)
        # Checkpoints covering these events would no longer verify; remove any created over them.
        conn.execute(text(
            "DELETE FROM anchor_checkpoints c WHERE EXISTS (SELECT 1 FROM financial_events e "
            "WHERE e.booking_id = ANY(CAST(:ids AS uuid[])) AND e.sequence BETWEEN c.first_sequence AND c.last_sequence)"), ids)
        conn.execute(text("DELETE FROM financial_events WHERE booking_id = ANY(CAST(:ids AS uuid[]))"), ids)
        conn.execute(text("DELETE FROM audit_events WHERE entity_id IN (SELECT id FROM settlements WHERE booking_id = ANY(CAST(:ids AS uuid[])))"), ids)
        conn.execute(text("DELETE FROM settlements WHERE booking_id = ANY(CAST(:ids AS uuid[]))"), ids)
    finally:
        conn.execute(text("ALTER TABLE settlements ENABLE TRIGGER trg_settlements_immutable"))
        for t in APPEND_ONLY:
            conn.execute(text(f"ALTER TABLE {t} ENABLE TRIGGER trg_{t}_append_only"))
        conn.execute(text("ALTER TABLE anchor_checkpoints ENABLE TRIGGER trg_anchor_checkpoints_guard"))
