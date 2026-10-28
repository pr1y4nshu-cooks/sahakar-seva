"""Concurrency: two simultaneous confirmations of overlapping bookings for one worker.

Unlike the other DB tests this needs real commits visible across connections, so it writes its own
uniquely-tagged rows to the *isolated test database* and deletes them in ``finally``. The session
leak check in conftest.py fails the run if anything is left behind.
"""

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.user import User
from app.services import booking_service
from trust_cleanup import purge_trust_rows


@pytest.fixture
def committed_pair(test_engine: Engine):
    tag = uuid.uuid4().hex[:8]
    ids = {k: uuid.uuid4() for k in ("worker_user", "c1", "c2", "wp", "cat", "skill", "slot", "b1", "b2")}
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=5)
    end = start + timedelta(hours=2)
    with test_engine.begin() as conn:
        for key in ("worker_user", "c1", "c2"):
            conn.execute(
                text("INSERT INTO users (id, external_auth_id, display_name, email) VALUES (:id, :sub, :n, :e)"),
                {"id": ids[key], "sub": f"conc|{key}|{tag}", "n": key, "e": f"{key}-{tag}@concurrency.test"},
            )
        conn.execute(text("INSERT INTO worker_profiles (id, user_id, display_name) VALUES (:id, :u, 'Conc Worker')"),
                     {"id": ids["wp"], "u": ids["worker_user"]})
        conn.execute(text("INSERT INTO service_categories (id, slug, name) VALUES (:id, :s, :n)"),
                     {"id": ids["cat"], "s": f"conc-{tag}", "n": f"Conc {tag}"})
        conn.execute(text("INSERT INTO skills (id, category_id, slug, name) VALUES (:id, :c, :s, :n)"),
                     {"id": ids["skill"], "c": ids["cat"], "s": f"conc-skill-{tag}", "n": f"Conc skill {tag}"})
        conn.execute(text("INSERT INTO availability_slots (id, worker_profile_id, starts_at, ends_at) VALUES (:id, :wp, :s, :e)"),
                     {"id": ids["slot"], "wp": ids["wp"], "s": start, "e": end})
        for b, c in (("b1", "c1"), ("b2", "c2")):
            conn.execute(
                text(
                    "INSERT INTO bookings (id, customer_user_id, worker_profile_id, origin, slot_id, skill_id, starts_at, ends_at, "
                    "locality, address_details, price_paise, fee_bps, fee_paise, payout_paise, status) VALUES "
                    "(:id, :c, :wp, 'direct', :slot, :skill, :s, :e, 'Koramangala', 'addr', 60000, 1000, 6000, 54000, 'requested')"
                ),
                {"id": ids[b], "c": ids[c], "wp": ids["wp"], "slot": ids["slot"], "skill": ids["skill"], "s": start, "e": end},
            )
    try:
        yield ids
    finally:
        with test_engine.begin() as conn:
            purge_trust_rows(conn, [ids["b1"], ids["b2"]])
            conn.execute(text("DELETE FROM audit_events WHERE entity_id IN (:b1, :b2)"), {"b1": ids["b1"], "b2": ids["b2"]})
            conn.execute(text("DELETE FROM bookings WHERE id IN (:b1, :b2)"), {"b1": ids["b1"], "b2": ids["b2"]})
            conn.execute(text("DELETE FROM availability_slots WHERE id = :id"), {"id": ids["slot"]})
            conn.execute(text("DELETE FROM worker_profiles WHERE id = :id"), {"id": ids["wp"]})
            conn.execute(text("DELETE FROM skills WHERE id = :id"), {"id": ids["skill"]})
            conn.execute(text("DELETE FROM service_categories WHERE id = :id"), {"id": ids["cat"]})
            conn.execute(text("DELETE FROM users WHERE id IN (:a, :b, :c)"), {"a": ids["worker_user"], "b": ids["c1"], "c": ids["c2"]})


def _statuses(engine: Engine, ids) -> list[str]:
    with engine.connect() as conn:
        return sorted(conn.execute(text("SELECT status FROM bookings WHERE id IN (:a, :b)"), {"a": ids["b1"], "b": ids["b2"]}).scalars())


def test_simultaneous_accepts_through_service_confirm_exactly_one(test_engine: Engine, committed_pair) -> None:
    ids = committed_pair
    barrier = threading.Barrier(2)
    outcomes: dict[str, str] = {}

    def accept(key: str) -> None:
        with Session(test_engine) as db:
            worker = db.get(User, ids["worker_user"])
            barrier.wait()
            try:
                booking_service.transition(db, worker, ids[key], "accept")
                outcomes[key] = "confirmed"
            except ApiError as exc:
                outcomes[key] = exc.detail["error"]["code"]

    threads = [threading.Thread(target=accept, args=(k,)) for k in ("b1", "b2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(outcomes.values()) == ["BOOKING_CONFLICT", "confirmed"]
    assert _statuses(test_engine, ids) == ["confirmed", "requested"]


def test_exclusion_constraint_blocks_concurrent_raw_confirmations(test_engine: Engine, committed_pair) -> None:
    """Even code that bypasses the service (no row lock) cannot double-confirm: the DB serialises it."""
    ids = committed_pair
    first_updated = threading.Event()
    result: dict[str, object] = {}

    conn1 = test_engine.connect()
    tx1 = conn1.begin()
    conn1.execute(text("UPDATE bookings SET status='confirmed' WHERE id=:id"), {"id": ids["b1"]})

    def second() -> None:
        with test_engine.connect() as conn2:
            first_updated.wait()
            try:
                with conn2.begin():
                    conn2.execute(text("SET LOCAL lock_timeout = '20s'"))
                    conn2.execute(text("UPDATE bookings SET status='confirmed' WHERE id=:id"), {"id": ids["b2"]})
                result["second"] = "committed"
            except IntegrityError as exc:
                result["second"] = type(exc.orig).__name__

    t = threading.Thread(target=second)
    t.start()
    first_updated.set()
    t.join(timeout=1)  # the second transaction must still be waiting on the first
    assert t.is_alive()
    tx1.commit()
    conn1.close()
    t.join(timeout=30)
    assert result["second"] == "ExclusionViolation"
    assert _statuses(test_engine, ids) == ["confirmed", "requested"]
