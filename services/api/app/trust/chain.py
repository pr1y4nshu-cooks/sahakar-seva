"""Append-only financial event chain (format v1).

``append_event`` is the only writer. It serialises writers with a transaction-scoped PostgreSQL advisory
lock, so two concurrent transactions can never compute the same sequence number or previous hash; the
UNIQUE constraints on ``sequence``, ``previous_event_hash`` and ``event_hash`` are the database-level
backstop. The lock is held until the caller's transaction ends, which keeps sequence order equal to
commit order.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.trust import FinancialEvent
from app.trust import crypto

CHAIN_LOCK_KEY = 0x5A4B_0001  # pg_advisory_xact_lock key for the financial event chain
CHECKPOINT_LOCK_KEY = 0x5A4B_0002


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def advisory_lock(db: Session, key: int) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


def _uuid(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def append_event(
    db: Session,
    *,
    event_type: str,
    booking_id: UUID | None,
    actor_role: str,
    actor_user_id: UUID | None,
    data: dict[str, Any],
    settlement_id: UUID | None = None,
    dispute_id: UUID | None = None,
    event_id: UUID | None = None,
) -> FinancialEvent:
    advisory_lock(db, CHAIN_LOCK_KEY)
    db.flush()
    head = db.execute(
        select(FinancialEvent.sequence, FinancialEvent.event_hash).order_by(FinancialEvent.sequence.desc()).limit(1)
    ).first()
    sequence = (head.sequence + 1) if head else 1
    previous_hash = head.event_hash if head else crypto.GENESIS_HASH

    booking_index, booking_previous = None, None
    if booking_id is not None:
        last = db.execute(
            select(FinancialEvent.booking_event_index, FinancialEvent.event_hash)
            .where(FinancialEvent.booking_id == booking_id)
            .order_by(FinancialEvent.booking_event_index.desc())
            .limit(1)
        ).first()
        booking_index = (last.booking_event_index + 1) if last else 0
        booking_previous = last.event_hash if last else None

    event_id = event_id or uuid4()
    occurred = datetime.now(timezone.utc)
    payload = {
        "format": crypto.EVENT_FORMAT,
        "event_id": str(event_id),
        "event_type": event_type,
        "occurred_at": iso(occurred),
        "booking_id": _uuid(booking_id),
        "booking_event_index": booking_index,
        "booking_previous_event_hash": booking_previous,
        "currency": "INR",
        "actor": {"role": actor_role, "user_id": _uuid(actor_user_id)},
        "data": data,
    }
    canonical = crypto.canonical(payload)
    p_hash = crypto.sha256_hex(crypto.PAYLOAD_DOMAIN + canonical)
    event = FinancialEvent(
        id=event_id,
        sequence=sequence,
        event_type=event_type,
        format_version=crypto.EVENT_FORMAT,
        hash_alg=crypto.HASH_ALG,
        booking_id=booking_id,
        booking_event_index=booking_index,
        settlement_id=settlement_id,
        dispute_id=dispute_id,
        payload_canonical=canonical.decode("utf-8"),
        payload_hash=p_hash,
        previous_event_hash=previous_hash,
        event_hash=crypto.event_hash(sequence, previous_hash, p_hash),
        created_at=occurred,
    )
    db.add(event)
    db.flush()
    return event


def booking_events(db: Session, booking_id: UUID) -> list[FinancialEvent]:
    return list(
        db.scalars(
            select(FinancialEvent).where(FinancialEvent.booking_id == booking_id).order_by(FinancialEvent.sequence)
        )
    )
