"""Server-side integrity verification of the financial event chain, checkpoints and ledger.

``verify_records`` is a pure function over plain dicts so that tests (and auditors) can tamper with copies
and see exactly what is detected. ``load_records`` reads the database into that shape.

What this can and cannot show: a chain that validates against itself proves internal consistency only.
An operator who rewrites every row and every hash can produce a new self-consistent chain. Detection of
such a rewrite needs evidence the operator cannot also rewrite: an RFC 3161 timestamp over a checkpoint
digest, or a receipt a participant downloaded earlier (scripts/verify_receipt.py --compare).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.marketplace import Settlement
from app.models.trust import AnchorCheckpoint, FinancialEvent, LedgerEntry, LedgerTransaction
from app.trust import crypto


def _problem(code: str, detail: str, **ref: Any) -> dict:
    return {"code": code, "detail": detail, **ref}


def verify_event_chain(events: list[dict]) -> list[dict]:
    """events: dicts with sequence, previous_event_hash, payload_canonical, payload_hash, event_hash,
    event_type, booking_id (str|None). Must be the complete chain from sequence 1, ordered as stored."""
    problems: list[dict] = []
    previous = crypto.GENESIS_HASH
    booking_heads: dict[str, tuple[int, str]] = {}
    for position, ev in enumerate(events):
        seq = ev["sequence"]
        if seq != position + 1:
            problems.append(_problem("SEQUENCE_GAP_OR_REORDER", f"expected sequence {position + 1}, found {seq}", sequence=seq))
        try:
            payload = json.loads(ev["payload_canonical"])
            recanonical = crypto.canonical(payload).decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - any parse failure is tampering
            problems.append(_problem("PAYLOAD_UNPARSEABLE", str(exc), sequence=seq))
            previous = ev["event_hash"]
            continue
        if recanonical != ev["payload_canonical"]:
            problems.append(_problem("PAYLOAD_NOT_CANONICAL", "stored payload is not in canonical form", sequence=seq))
        p_hash = crypto.payload_hash(payload)
        if p_hash != ev["payload_hash"]:
            problems.append(_problem("PAYLOAD_HASH_MISMATCH", "payload does not match its committed hash", sequence=seq))
        if ev["previous_event_hash"] != previous:
            problems.append(_problem("CHAIN_BROKEN", "previous_event_hash does not link to the prior event", sequence=seq))
        if crypto.event_hash(seq, ev["previous_event_hash"], p_hash) != ev["event_hash"]:
            problems.append(_problem("EVENT_HASH_MISMATCH", "event hash does not recompute", sequence=seq))
        if payload.get("event_type") != ev["event_type"] or payload.get("booking_id") != ev["booking_id"]:
            problems.append(_problem("COLUMN_PAYLOAD_MISMATCH", "indexed columns disagree with the committed payload", sequence=seq))
        booking = payload.get("booking_id")
        if booking:
            idx, prev_hash = booking_heads.get(booking, (-1, None))
            if payload.get("booking_event_index") != idx + 1 or payload.get("booking_previous_event_hash") != prev_hash:
                problems.append(_problem("BOOKING_CHAIN_BROKEN", "per-booking event index/link is not continuous", sequence=seq, booking_id=booking))
            booking_heads[booking] = (payload.get("booking_event_index", idx + 1), ev["event_hash"])
        previous = ev["event_hash"]
    return problems


def verify_checkpoints(checkpoints: list[dict], events: list[dict]) -> list[dict]:
    problems: list[dict] = []
    by_seq = {e["sequence"]: e for e in events}
    previous_digest = crypto.GENESIS_HASH
    expected_first = 1
    for i, cp in enumerate(sorted(checkpoints, key=lambda c: c["checkpoint_index"])):
        ref = {"checkpoint_index": cp["checkpoint_index"]}
        if cp["checkpoint_index"] != i + 1:
            problems.append(_problem("CHECKPOINT_INDEX_GAP", "checkpoint indices are not contiguous", **ref))
        try:
            body = json.loads(cp["body_canonical"])
        except ValueError:
            problems.append(_problem("CHECKPOINT_BODY_UNPARSEABLE", "checkpoint body is not JSON", **ref))
            continue
        if crypto.checkpoint_digest(body) != cp["digest"]:
            problems.append(_problem("CHECKPOINT_DIGEST_MISMATCH", "checkpoint digest does not recompute", **ref))
        fields = ("first_sequence", "last_sequence", "merkle_root", "last_event_hash", "previous_checkpoint_digest")
        if any(body.get(f) != cp[f] for f in fields):
            problems.append(_problem("CHECKPOINT_COLUMNS_MISMATCH", "indexed columns disagree with the committed body", **ref))
        if body.get("previous_checkpoint_digest") != previous_digest:
            problems.append(_problem("CHECKPOINT_CHAIN_BROKEN", "previous checkpoint digest does not link", **ref))
        if body.get("first_sequence") != expected_first:
            problems.append(_problem("CHECKPOINT_RANGE_GAP", "checkpoint ranges are not contiguous", **ref))
        first, last = body.get("first_sequence", 0), body.get("last_sequence", -1)
        covered = [by_seq.get(s) for s in range(first, last + 1)]
        if any(e is None for e in covered):
            problems.append(_problem("EVENTS_MISSING_FROM_CHECKPOINT_RANGE", "events inside a checkpointed range are missing", **ref))
        else:
            if crypto.merkle_root([e["event_hash"] for e in covered]) != body.get("merkle_root"):
                problems.append(_problem("MERKLE_ROOT_MISMATCH", "events no longer hash to the checkpointed Merkle root", **ref))
            if covered and covered[-1]["event_hash"] != body.get("last_event_hash"):
                problems.append(_problem("CHECKPOINT_HEAD_MISMATCH", "last event hash differs from the checkpoint", **ref))
        previous_digest = cp["digest"]
        expected_first = last + 1
    return problems


def verify_ledger(transactions: list[dict], settlements: dict[str, dict], events_by_id: dict[str, dict]) -> list[dict]:
    """transactions: dicts with id, transaction_type, amount_paise, settlement_id, source_event_id, entries[]."""
    problems: list[dict] = []
    for tx in transactions:
        ref = {"transaction_id": tx["id"]}
        debits = sum(e["amount_paise"] for e in tx["entries"] if e["direction"] == "debit")
        credits = sum(e["amount_paise"] for e in tx["entries"] if e["direction"] == "credit")
        if debits != credits or debits != tx["amount_paise"] or len(tx["entries"]) < 2:
            problems.append(_problem("LEDGER_UNBALANCED", f"debits {debits} / credits {credits} / amount {tx['amount_paise']}", **ref))
        event = events_by_id.get(tx["source_event_id"])
        if event is None:
            problems.append(_problem("LEDGER_SOURCE_EVENT_MISSING", "source event not found in the chain", **ref))
            continue
        committed = json.loads(event["payload_canonical"])["data"].get("ledger_transaction", {})
        committed_entries = [(e["account"], e["direction"], e["amount_paise"]) for e in committed.get("entries", [])]
        stored_entries = [(e["account_code"], e["direction"], e["amount_paise"]) for e in sorted(tx["entries"], key=lambda e: e["entry_index"])]
        if committed.get("id") != tx["id"] or committed.get("amount_paise") != tx["amount_paise"] or committed_entries != stored_entries:
            problems.append(_problem("LEDGER_DIFFERS_FROM_COMMITTED_EVENT", "ledger rows differ from the hash-committed event", **ref))
        if tx["transaction_type"] == "simulated_booking_settlement":
            s = settlements.get(tx["settlement_id"])
            amounts = {e[0]: e[2] for e in stored_entries}
            paid_by_parties = amounts.get("simulated_customer_payment_clearing", 0) + amounts.get("simulated_business_payment_clearing", 0)
            payout = amounts.get("simulated_worker_entitlement", 0)
            if s is None or (s["gross_paise"], s["payout_paise"], s["fee_paise"]) != (paid_by_parties, payout, paid_by_parties - payout):
                problems.append(_problem("SETTLEMENT_LEDGER_MISMATCH", "settlement amounts differ from ledger allocations", **ref))
    return problems


def verify_records(events: list[dict], checkpoints: list[dict], transactions: list[dict], settlements: dict[str, dict]) -> dict:
    problems = (
        verify_event_chain(events)
        + verify_checkpoints(checkpoints, events)
        + verify_ledger(transactions, settlements, {e["id"]: e for e in events})
    )
    return {
        "ok": not problems,
        "events_checked": len(events),
        "checkpoints_checked": len(checkpoints),
        "ledger_transactions_checked": len(transactions),
        "problems": problems,
        "scope_note": (
            "Internal consistency only. Independent assurance requires RFC 3161 timestamps over checkpoint "
            "digests or participant-held receipts."
        ),
    }


def load_records(db: Session) -> tuple[list[dict], list[dict], list[dict], dict[str, dict]]:
    events = [
        {
            "id": str(e.id), "sequence": e.sequence, "event_type": e.event_type,
            "booking_id": str(e.booking_id) if e.booking_id else None,
            "payload_canonical": e.payload_canonical, "payload_hash": e.payload_hash,
            "previous_event_hash": e.previous_event_hash, "event_hash": e.event_hash,
        }
        for e in db.scalars(select(FinancialEvent).order_by(FinancialEvent.sequence))
    ]
    checkpoints = [
        {
            "checkpoint_index": c.checkpoint_index, "body_canonical": c.body_canonical, "digest": c.digest,
            "first_sequence": c.first_sequence, "last_sequence": c.last_sequence, "merkle_root": c.merkle_root,
            "last_event_hash": c.last_event_hash, "previous_checkpoint_digest": c.previous_checkpoint_digest,
        }
        for c in db.scalars(select(AnchorCheckpoint).order_by(AnchorCheckpoint.checkpoint_index))
    ]
    entries: dict[str, list[dict]] = {}
    for en in db.scalars(select(LedgerEntry)):
        entries.setdefault(str(en.transaction_id), []).append(
            {"entry_index": en.entry_index, "account_code": en.account_code, "direction": en.direction, "amount_paise": en.amount_paise}
        )
    transactions = [
        {
            "id": str(t.id), "transaction_type": t.transaction_type, "amount_paise": t.amount_paise,
            "settlement_id": str(t.settlement_id) if t.settlement_id else None,
            "source_event_id": str(t.source_event_id), "entries": entries.get(str(t.id), []),
        }
        for t in db.scalars(select(LedgerTransaction))
    ]
    settlement_ids = [t["settlement_id"] for t in transactions if t["settlement_id"]]
    settlements = {
        str(s.id): {"gross_paise": s.gross_paise, "fee_paise": s.fee_paise, "payout_paise": s.payout_paise}
        for s in db.scalars(select(Settlement).where(Settlement.id.in_(settlement_ids)))
    } if settlement_ids else {}
    return events, checkpoints, transactions, settlements


def verify_database(db: Session) -> dict:
    return verify_records(*load_records(db))
