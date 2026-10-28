"""Checkpoints over the financial event chain and their external RFC 3161 anchoring (transactional outbox).

Flow (no network call ever runs inside a database transaction):
1. ``create_checkpoint``: one short transaction. Verifies the not-yet-checkpointed events (hashes and
   links), computes a Merkle root and the checkpoint digest, and inserts the checkpoint with status
   ANCHOR_PENDING (TSA configured) or LOCAL_ONLY (no TSA). This row *is* the outbox entry.
2. ``process_due``: per checkpoint, (a) a short transaction claims it (FOR UPDATE SKIP LOCKED), stores a
   fresh nonce, marks ANCHOR_SUBMITTED and commits; (b) the digest is sent to the TSA with no
   transaction open; (c) the response is verified against the pinned trust anchor; (d) a second short
   transaction records EXTERNALLY_ANCHORED with the evidence, or PROOF_INVALID / ANCHOR_PENDING with a
   bounded exponential backoff, ending in ANCHOR_FAILED after ``ANCHOR_MAX_ATTEMPTS``.
Booking completion never waits for any of this.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.trust import AnchorCheckpoint, FinancialEvent
from app.trust import crypto, timestamping
from app.trust.chain import CHECKPOINT_LOCK_KEY, advisory_lock, iso

log = logging.getLogger("sahakar.anchoring")

STALE_SUBMISSION = timedelta(minutes=5)
STATUS_LABELS = {
    "LOCAL_ONLY": "Local integrity only — no external timestamp service configured",
    "ANCHOR_PENDING": "External timestamp pending",
    "ANCHOR_SUBMITTED": "External timestamp requested — awaiting verification",
    "EXTERNALLY_ANCHORED": "External timestamp verified",
    "ANCHOR_FAILED": "External timestamp failed — local integrity only",
    "PROOF_INVALID": "External timestamp response failed verification",
}


class ChainIntegrityError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_checkpoint(db: Session, settings: Settings, max_events: int = 1000) -> AnchorCheckpoint | None:
    """Checkpoint all committed events after the previous checkpoint. Caller commits."""
    advisory_lock(db, CHECKPOINT_LOCK_KEY)
    previous = db.scalar(select(AnchorCheckpoint).order_by(AnchorCheckpoint.checkpoint_index.desc()).limit(1))
    first = previous.last_sequence + 1 if previous else 1
    events = list(
        db.scalars(
            select(FinancialEvent).where(FinancialEvent.sequence >= first).order_by(FinancialEvent.sequence).limit(max_events)
        )
    )
    if not events:
        return None

    prev_hash = previous.last_event_hash if previous else crypto.GENESIS_HASH
    for offset, ev in enumerate(events):
        if ev.sequence != first + offset:
            raise ChainIntegrityError(f"sequence gap before {ev.sequence}; refusing to checkpoint")
        payload = json.loads(ev.payload_canonical)
        if crypto.payload_hash(payload) != ev.payload_hash or ev.previous_event_hash != prev_hash or crypto.event_hash(
            ev.sequence, ev.previous_event_hash, ev.payload_hash
        ) != ev.event_hash:
            raise ChainIntegrityError(f"event {ev.sequence} does not verify; refusing to checkpoint")
        prev_hash = ev.event_hash

    created = _now()
    body = {
        "format": crypto.CHECKPOINT_FORMAT,
        "hash_alg": crypto.HASH_ALG,
        "checkpoint_index": (previous.checkpoint_index + 1) if previous else 1,
        "first_sequence": first,
        "last_sequence": events[-1].sequence,
        "event_count": len(events),
        "merkle_root": crypto.merkle_root([e.event_hash for e in events]),
        "merkle_construction": "RFC 9162 section 2.1.1 over event_hash leaves",
        "last_event_hash": events[-1].event_hash,
        "previous_checkpoint_digest": previous.digest if previous else crypto.GENESIS_HASH,
        "created_at": iso(created),
    }
    checkpoint = AnchorCheckpoint(
        checkpoint_index=body["checkpoint_index"],
        format_version=crypto.CHECKPOINT_FORMAT,
        hash_alg=crypto.HASH_ALG,
        first_sequence=body["first_sequence"],
        last_sequence=body["last_sequence"],
        event_count=body["event_count"],
        merkle_root=body["merkle_root"],
        last_event_hash=body["last_event_hash"],
        previous_checkpoint_digest=body["previous_checkpoint_digest"],
        body_canonical=crypto.canonical(body).decode("utf-8"),
        digest=crypto.checkpoint_digest(body),
        created_at=created,
        anchor_status="ANCHOR_PENDING" if settings.tsa_configured else "LOCAL_ONLY",
        attempt_count=0,
        next_attempt_at=created if settings.tsa_configured else None,
    )
    db.add(checkpoint)
    db.flush()
    return checkpoint


def promote_local_only(db: Session, settings: Settings) -> int:
    """When a TSA becomes configured, queue LOCAL_ONLY checkpoints for anchoring. Caller commits."""
    if not settings.tsa_configured:
        return 0
    rows = list(db.scalars(select(AnchorCheckpoint).where(AnchorCheckpoint.anchor_status == "LOCAL_ONLY").with_for_update(skip_locked=True)))
    for cp in rows:
        cp.anchor_status = "ANCHOR_PENDING"
        cp.next_attempt_at = _now()
    return len(rows)


def _backoff(settings: Settings, attempts: int) -> datetime:
    return _now() + timedelta(seconds=min(settings.anchor_retry_base_seconds * 2 ** max(attempts - 1, 0), 3600))


def _claim(db: Session, settings: Settings) -> tuple | None:
    now = _now()
    cp = db.scalar(
        select(AnchorCheckpoint)
        .where(
            or_(
                (AnchorCheckpoint.anchor_status.in_(("ANCHOR_PENDING", "PROOF_INVALID")))
                & (AnchorCheckpoint.attempt_count < settings.anchor_max_attempts)
                & ((AnchorCheckpoint.next_attempt_at.is_(None)) | (AnchorCheckpoint.next_attempt_at <= now)),
                (AnchorCheckpoint.anchor_status == "ANCHOR_SUBMITTED") & (AnchorCheckpoint.submitted_at < now - STALE_SUBMISSION),
            )
        )
        .order_by(AnchorCheckpoint.checkpoint_index)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if cp is None:
        return None
    request = timestamping.build_request(cp.digest)
    cp.anchor_status = "ANCHOR_SUBMITTED"
    cp.request_nonce = str(request.nonce)
    cp.tsa_url = settings.tsa_url
    cp.tsa_name = settings.tsa_name or settings.tsa_url
    cp.submitted_at = now
    cp.attempt_count = cp.attempt_count + 1
    claimed = (cp.id, cp.digest, request, cp.attempt_count)
    db.commit()
    return claimed


def _record(db: Session, settings: Settings, checkpoint_id, nonce: int, outcome: dict) -> str:
    cp = db.scalar(select(AnchorCheckpoint).where(AnchorCheckpoint.id == checkpoint_id).with_for_update())
    if cp is None or cp.anchor_status != "ANCHOR_SUBMITTED" or cp.request_nonce != str(nonce):
        db.rollback()
        return "superseded"
    if outcome["kind"] == "verified":
        v: timestamping.VerifiedTimestamp = outcome["verified"]
        cp.anchor_status = "EXTERNALLY_ANCHORED"
        cp.tsa_response_b64 = timestamping.b64(outcome["der"])
        cp.tsa_gen_time = v.gen_time
        cp.tsa_serial = v.serial_number[:80]
        cp.tsa_policy_oid = v.policy_oid[:80]
        cp.tsa_signer_subject = v.signer_subject
        cp.tsa_ca_fingerprint = timestamping.ca_fingerprint(settings.tsa_ca_file or "")
        cp.verified_at = _now()
        cp.last_error = None
        cp.next_attempt_at = None
    else:
        exhausted = cp.attempt_count >= settings.anchor_max_attempts
        if outcome["kind"] == "invalid":
            cp.anchor_status = "PROOF_INVALID"
        else:
            cp.anchor_status = "ANCHOR_FAILED" if exhausted else "ANCHOR_PENDING"
        cp.last_error = outcome["error"][:500]
        cp.next_attempt_at = None if exhausted else _backoff(settings, cp.attempt_count)
    status = cp.anchor_status
    db.commit()
    return status


def process_due(session_factory: Callable[[], Session], settings: Settings, limit: int = 5) -> list[dict]:
    results: list[dict] = []
    if not settings.tsa_configured:
        return results
    for _ in range(limit):
        with session_factory() as db:
            claimed = _claim(db, settings)
        if claimed is None:
            break
        checkpoint_id, digest, request, attempt = claimed
        # --- no database transaction is open from here until _record ---
        try:
            der = timestamping.submit(settings.tsa_url, request, settings.tsa_timeout_seconds)
            verified = timestamping.verify_response(der, digest, settings.tsa_ca_file, request.nonce)
            outcome = {"kind": "verified", "der": der, "verified": verified}
        except timestamping.TimestampVerificationError as exc:
            outcome = {"kind": "invalid", "error": f"proof invalid: {exc}"}
        except timestamping.TimestampError as exc:
            outcome = {"kind": "unavailable", "error": str(exc)}
        with session_factory() as db:
            status = _record(db, settings, checkpoint_id, request.nonce, outcome)
        log.info("checkpoint %s attempt %s -> %s", checkpoint_id, attempt, status)
        results.append({"checkpoint_id": str(checkpoint_id), "attempt": attempt, "status": status, "error": outcome.get("error")})
    return results


def retry_failed(db: Session, settings: Settings) -> int:
    """Operator action: re-queue ANCHOR_FAILED / PROOF_INVALID checkpoints with a fresh attempt budget."""
    if not settings.tsa_configured:
        return 0
    rows = list(db.scalars(select(AnchorCheckpoint).where(AnchorCheckpoint.anchor_status.in_(("ANCHOR_FAILED", "PROOF_INVALID")))))
    for cp in rows:
        cp.anchor_status = "ANCHOR_PENDING"
        cp.attempt_count = 0
        cp.next_attempt_at = _now()
    db.commit()
    return len(rows)


def run_cycle(session_factory: Callable[[], Session], settings: Settings) -> dict:
    """One worker cycle: checkpoint new events, queue LOCAL_ONLY if a TSA is now configured, submit due ones."""
    created = None
    with session_factory() as db:
        promoted = promote_local_only(db, settings)
        cp = create_checkpoint(db, settings)
        created = cp.checkpoint_index if cp else None
        db.commit()
    return {"created_checkpoint": created, "promoted": promoted, "anchoring": process_due(session_factory, settings)}
