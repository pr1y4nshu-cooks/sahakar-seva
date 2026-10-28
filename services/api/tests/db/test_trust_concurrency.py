"""Concurrency and real-COMMIT behaviour of the financial event chain and ledger.

These tests commit to the *isolated test database* (separate connections must see each other's work)
and remove exactly their own rows afterwards (trust_cleanup). The session leak check verifies that.
"""

import threading
import time
import uuid

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.trust import FinancialEvent, LedgerTransaction
from app.models.user import User
from app.services import booking_service
from app.trust import integrity
from app.trust.chain import append_event
from test_booking_concurrency import committed_pair  # noqa: F401  (fixture)
from trust_cleanup import purge_events


def test_concurrent_event_appends_get_distinct_sequences_and_one_chain(test_engine: Engine) -> None:
    barrier = threading.Barrier(2)
    written: dict[str, tuple] = {}
    errors: list[BaseException] = []

    def writer(name: str, hold_s: float) -> None:
        try:
            with Session(test_engine) as db:
                barrier.wait()
                ev = append_event(db, event_type="booking_cancelled", booking_id=None, actor_role="system",
                                  actor_user_id=None, data={"concurrency_probe": name})
                time.sleep(hold_s)  # keep the transaction (and the chain lock) open while the other waits
                written[name] = (ev.id, ev.sequence, ev.previous_event_hash, ev.event_hash)
                db.commit()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=("a", 0.5)), threading.Thread(target=writer, args=("b", 0.5))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    try:
        assert not errors, errors
        (_, s1, p1, h1), (_, s2, p2, h2) = sorted(written.values(), key=lambda w: w[1])
        assert s2 == s1 + 1, "sequences must be distinct and adjacent"
        assert p2 == h1, "the later event must link to the earlier one (no fork)"
        with Session(test_engine) as db:
            report = integrity.verify_database(db)
            assert report["ok"], report["problems"]
    finally:
        with test_engine.begin() as conn:
            purge_events(conn, [w[0] for w in written.values()])


def test_real_commit_of_completion_passes_deferred_balance_check(test_engine: Engine, committed_pair) -> None:  # noqa: F811
    """Ordinary DB tests roll back, so deferred constraint triggers never fire. This one commits."""
    ids = committed_pair
    with Session(test_engine) as db:
        worker = db.get(User, ids["worker_user"])
        customer = db.get(User, ids["c1"])
        booking_service.transition(db, worker, ids["b1"], "accept")
        booking_service.transition(db, worker, ids["b1"], "start")
        done = booking_service.transition(db, customer, ids["b1"], "complete")  # COMMIT runs the deferred check
    assert done["status"] == "completed" and done["evidence"]["ledger_status"] == "posted"
    assert done["agreement"]["evidence_level"] == "legacy_snapshot"  # raw-inserted booking = pre-0005 style
    with Session(test_engine) as db:
        tx = db.scalar(select(LedgerTransaction).where(LedgerTransaction.booking_id == ids["b1"]))
        assert tx is not None and tx.amount_paise == 60000
        events = list(db.scalars(select(FinancialEvent.event_type).where(FinancialEvent.booking_id == ids["b1"]).order_by(FinancialEvent.sequence)))
        assert events[-1] == "simulated_settlement_recorded"
        assert integrity.verify_database(db)["ok"]
        # An unbalanced posting is refused at COMMIT by the database itself.
        with test_engine.connect() as conn:
            trans = conn.begin()
            bad = uuid.uuid4()
            conn.execute(text(
                "INSERT INTO financial_ledger_transactions (id, booking_id, reverses_transaction_id, transaction_type, currency, "
                "amount_paise, idempotency_key, source_event_id) VALUES (:id, :b, :r, 'simulated_settlement_reversal', 'INR', 100, :k, "
                "(SELECT id FROM financial_events WHERE booking_id = :b ORDER BY sequence LIMIT 1))"),
                {"id": bad, "b": ids["b1"], "r": tx.id, "k": f"probe-{bad}"})
            try:
                trans.commit()
                committed = True
            except Exception as exc:  # noqa: BLE001
                committed = False
                assert "not balanced" in str(exc)
            assert committed is False
