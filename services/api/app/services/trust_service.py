"""Versioned price agreements, quote acceptance, ledger posting and per-booking evidence views.

Single source of truth: every financial number a customer or worker sees for a booking comes from the
current ``price_quote_versions`` row (mirrored into the booking's price columns in the same transaction)
and, after completion, from the settlement + balanced ledger transaction. There is no separate
"worker-visible" price. Quotes are priced by the fee policy that was active when the quote was created
(``app.trust.pricing``); the full policy definition and its line items are committed to the hash chain.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, conflict, unprocessable
from app.models.marketplace import SIMULATED_PAYMENT_LABEL, Booking, Dispute, Job, Settlement
from app.models.trust import (
    AnchorCheckpoint,
    FeePolicy,
    FinancialEvent,
    LedgerEntry,
    LedgerTransaction,
    PriceQuoteVersion,
    QuoteAcceptance,
)
from app.models.user import User
from app.services import fee_policy_service as fps
from app.trust import crypto, pricing
from app.trust.anchoring import STATUS_LABELS
from app.trust.chain import append_event, booking_events, iso

PAYMENT_EVIDENCE = "SIMULATED — no payment provider is connected; no real money was collected or paid out."
TAX_NOTE = "No taxes are modeled. Displayed totals do not include GST or any other tax."
PROCESSING_NOTE = "Processing charges, if listed, are modeled pass-through costs. No payment processor is connected."
LEGACY_NOTE = (
    "Legacy record: this booking was priced before versioned agreements existed. Its price snapshot is "
    "shown as stored; no quote acceptance, ledger or hash-chain evidence was collected for it."
)
STATIC_RULES = {
    "assessed_when": "Charges are recorded only when a booking is completed and its simulated settlement is posted.",
    "cancellations": "Cancelled or declined bookings record no settlement and no charges.",
    "disputes": (
        "Opening a dispute does not change the recorded charges. A human reviewer may record a full reversal of the "
        "simulated settlement; the original entries stay in the ledger and a reversing transaction is added."
    ),
    "existing_agreements": (
        "Each booking keeps the policy, version and line items written into its accepted quote. Activating a new "
        "policy affects only quotes created afterwards; confirmed bookings are never re-priced."
    ),
    "bearers": {
        "customer": "added to the customer total",
        "worker": "deducted from the worker's payout",
        "business": "added to the total and billed to the organization the booking is for",
        "platform": "absorbed by the platform (does not change what either party sees)",
    },
    "tax_note": TAX_NOTE,
    "processing_note": PROCESSING_NOTE,
    "payments_mode": "simulated",
    "payments_note": "Payments are simulated in this pilot. No money is collected, held or paid out.",
    "free_for_individuals": ["Registration", "Declaring skills", "Browsing and applying to jobs", "Posting jobs"],
    "not_final_pricing": "Final commercial pricing has not been decided. Policies marked as examples are illustrative.",
}
ILLUSTRATIVE_SERVICE_PRICES = (20000, 50000, 200000)


# --- fee policy views ----------------------------------------------------------------------


def _examples(fp: FeePolicy) -> list[dict]:
    out = []
    for price in ILLUSTRATIVE_SERVICE_PRICES:
        try:
            ev = fps.evaluate(fp, price, "direct", False)
        except ApiError as exc:
            out.append({"service_price_paise": price, "error": exc.detail["error"]["message"]})
            continue
        out.append({k: ev[k] for k in ("service_price_paise", "customer_total_paise", "worker_payout_paise",
                                       "platform_fee_paise", "processing_charge_paise", "waived_paise")})
    return out


def fee_policy(db: Session) -> dict:
    """Public description of the ACTIVE default policy. Nothing here is hardcoded."""
    fp = fps.active_policy(db)
    return {
        "active_policy": fps.policy_view(fp) if fp else None,
        "examples": _examples(fp) if fp else [],
        "examples_note": "Illustrative service prices evaluated with the active policy, for a direct booking.",
        "rules": STATIC_RULES,
    }


def fee_policy_history(db: Session) -> list[dict]:
    rows = db.scalars(select(FeePolicy).where(FeePolicy.scope == "default", FeePolicy.status != "draft")
                      .order_by(FeePolicy.activated_at.desc()))
    return [{k: v for k, v in fps.policy_view(fp).items() if k not in ("definition",)} for fp in rows]


def preview(db: Session, service_price_paise: int, origin: str, organization_id: UUID | None) -> dict:
    fp = fps.require_active(db, organization_id)
    ev = fps.evaluate(fp, service_price_paise, origin, organization_id is not None)
    return {"policy": {"policy_id": fp.policy_id, "version": fp.version, "label": fp.label, "is_example": fp.is_example,
                       "pricing_model": fp.pricing_model, "definition_hash": fp.definition_hash}, "evaluation": ev,
            "note": "Preview only. The binding quote is computed and stored by the server when the booking is created."}


def simulate(definition: dict, prices: list[int], origin: str, for_organization: bool,
             recorded: list[tuple[int, str, bool]] | None) -> dict:
    """Evaluate a candidate (unsaved) policy. Pure: nothing is stored."""
    normalized = pricing.normalize(definition)
    at = pricing.evaluated_at(datetime.now(timezone.utc))

    def run(rows: list[tuple[int, str, bool]]) -> dict:
        items, totals = [], {"bookings": 0, "refused": 0, "service_price_paise": 0, "customer_total_paise": 0,
                             "worker_payout_paise": 0, "platform_fee_paise": 0, "processing_charge_paise": 0,
                             "platform_borne_paise": 0, "waived_paise": 0}
        for price, org_origin, org in rows:
            try:
                ev = pricing.evaluate(normalized, price, org_origin, org, at)
            except pricing.PricingError as exc:
                totals["refused"] += 1
                items.append({"service_price_paise": price, "origin": org_origin, "for_organization": org, "refused": exc.code})
                continue
            totals["bookings"] += 1
            for k in list(totals)[2:]:
                totals[k] += ev[k]
            items.append({"service_price_paise": price, "origin": org_origin, "for_organization": org,
                          **{k: ev[k] for k in ("customer_total_paise", "worker_payout_paise", "platform_fee_paise",
                                                "processing_charge_paise", "platform_borne_paise", "waived_paise",
                                                "effective_charge_bps")}})
        return {"items": items, "totals": totals}

    out = {"pricing_model": pricing.pricing_model(normalized), "definition_hash": pricing.definition_hash(normalized),
           "normalized_definition": normalized, "evaluated_at": at,
           "samples": run([(p, origin, for_organization) for p in prices])}
    if recorded is not None:
        out["recorded_bookings"] = run(recorded)
        out["recorded_note"] = ("Hypothetical: recorded completed bookings re-priced under this candidate policy. "
                                "Their real agreements are unchanged.")
    return out


# --- quotes --------------------------------------------------------------------------------


def current_quote(db: Session, booking_id: UUID) -> PriceQuoteVersion | None:
    return db.scalar(
        select(PriceQuoteVersion)
        .where(PriceQuoteVersion.booking_id == booking_id)
        .order_by(PriceQuoteVersion.version.desc())
        .limit(1)
    )


def acceptances(db: Session, quote_id: UUID) -> dict[str, QuoteAcceptance]:
    return {a.role: a for a in db.scalars(select(QuoteAcceptance).where(QuoteAcceptance.quote_id == quote_id))}


def quote_lines(q: PriceQuoteVersion) -> list[dict]:
    """Line items for any quote; pre-0006 quotes are percentage, worker-borne."""
    if q.line_items_canonical:
        return json.loads(q.line_items_canonical)
    return [{"code": "platform_service_fee", "kind": "platform_fee", "label": "Platform fee", "bearer": "worker",
             "percent_bps": q.fee_bps, "fixed_paise": 0, "min_paise": None, "max_paise": None,
             "computed_paise": q.platform_fee_paise, "amount_paise": q.platform_fee_paise, "waived_by": None}]


def service_price(q: PriceQuoteVersion) -> int:
    return q.service_price_paise if q.service_price_paise is not None else q.customer_total_paise


def _evaluation_of(q: PriceQuoteVersion) -> dict:
    """Reconstruct the evaluation shape (for ledger postings) from a stored quote."""
    lines = quote_lines(q)
    by = lambda bearer: sum(l["amount_paise"] for l in lines if l["bearer"] == bearer)  # noqa: E731
    return {
        "service_price_paise": service_price(q), "customer_total_paise": q.customer_total_paise,
        "worker_payout_paise": q.worker_share_paise, "platform_fee_paise": q.platform_fee_paise,
        "processing_charge_paise": q.additional_charges_paise, "tax_paise": q.tax_paise,
        "business_borne_paise": by("business"), "platform_borne_paise": by("platform"),
    }


def _for_organization(db: Session, booking: Booking) -> UUID | None:
    if booking.job_id is None:
        return None
    return db.scalar(select(Job.organization_id).where(Job.id == booking.job_id))


def _quote_data(q: PriceQuoteVersion, booking: Booking, previous_version: int | None, extra: dict) -> dict:
    minutes = int((booking.ends_at - booking.starts_at).total_seconds() // 60)
    return {
        "quote": {
            "quote_id": str(q.id),
            "version": q.version,
            "previous_version": previous_version,
            "source": q.source,
            "pricing_basis": q.pricing_basis,
            "currency": q.currency,
            "service_price_paise": q.service_price_paise,
            "customer_total_paise": q.customer_total_paise,
            "worker_share_paise": q.worker_share_paise,
            "platform_fee_paise": q.platform_fee_paise,
            "additional_charges_paise": q.additional_charges_paise,
            "tax_paise": q.tax_paise,
            "taxes_modeled": q.taxes_modeled,
            "fee_bps": q.fee_bps,
            "fee_cap_bps": q.fee_cap_bps,
            "fee_policy_id": q.fee_policy_id,
            "fee_policy_version": q.fee_policy_version,
            "pricing_model": q.pricing_model,
            "line_items": json.loads(q.line_items_canonical) if q.line_items_canonical else None,
            **extra,
        },
        "service": {
            "skill_id": str(booking.skill_id),
            "origin": booking.origin,
            "starts_at": iso(booking.starts_at),
            "ends_at": iso(booking.ends_at),
            "duration_minutes": minutes,
        },
    }


def create_quote(
    db: Session,
    booking: Booking,
    *,
    source: str,
    pricing_basis: str,
    service_price_paise: int,
    initiator: User | None,
    initiator_role: str,
    policy: FeePolicy | None = None,
) -> PriceQuoteVersion:
    """Price with ``policy`` (default: the policy of the previous version, else the active one), write an
    immutable quote version, commit it to the event chain, and mirror it onto the booking."""
    previous = current_quote(db, booking.id)
    legacy = source == "legacy_snapshot"
    org_id = _for_organization(db, booking)
    extra: dict = {}
    if legacy:
        fee_paise = booking.fee_paise
        ev = {"customer_total_paise": booking.price_paise, "worker_payout_paise": booking.payout_paise,
              "platform_fee_paise": fee_paise, "processing_charge_paise": 0, "tax_paise": 0,
              "effective_charge_bps": booking.fee_bps, "max_total_charge_bps": max(booking.fee_bps, 0)}
        policy_id, policy_version, model, record_id, def_hash, lines_json, svc = (
            "legacy-mvp-snapshot", "pre-0005", None, None, None, None, None)
    else:
        if policy is None and previous is not None and previous.fee_policy_record_id is not None:
            policy = db.get(FeePolicy, previous.fee_policy_record_id)  # a revision keeps the agreed terms
        policy = policy or fps.require_active(db, org_id)
        ev = fps.evaluate(policy, service_price_paise, booking.origin, org_id is not None)
        policy_id, policy_version, model, record_id, def_hash = (
            policy.policy_id, str(policy.version), policy.pricing_model, policy.id, policy.definition_hash)
        lines_json = crypto.canonical(ev["lines"]).decode("utf-8")
        svc = service_price_paise
        extra = {"fee_policy_record_id": str(policy.id), "policy_definition_hash": policy.definition_hash,
                 "policy_definition": fps.definition(policy), "evaluated_at": ev["evaluated_at"],
                 "for_organization": org_id is not None, "is_example_policy": policy.is_example}
    total, payout = ev["customer_total_paise"], ev["worker_payout_paise"]
    charges = total - payout
    if (booking.price_paise, booking.fee_bps, booking.fee_paise, booking.payout_paise) != (total, ev["effective_charge_bps"], charges, payout):
        if booking.status != "requested":
            raise conflict("PRICE_LOCKED", "The agreed price of this booking can no longer change.")
        booking.price_paise, booking.fee_bps, booking.fee_paise, booking.payout_paise = (total, ev["effective_charge_bps"], charges, payout)
    version = previous.version + 1 if previous else 1
    quote_id, event_id = uuid4(), uuid4()
    q = PriceQuoteVersion(
        id=quote_id, booking_id=booking.id, version=version, source=source, pricing_basis=pricing_basis, currency="INR",
        customer_total_paise=total, worker_share_paise=payout, platform_fee_paise=ev["platform_fee_paise"],
        additional_charges_paise=ev["processing_charge_paise"], tax_paise=0, taxes_modeled=False,
        fee_bps=ev["effective_charge_bps"], fee_cap_bps=ev["max_total_charge_bps"],
        fee_policy_id=policy_id, fee_policy_version=policy_version,
        initiated_by_user_id=initiator.id if initiator else None, initiated_by_role=initiator_role, financial_event_id=event_id,
        service_price_paise=svc, fee_policy_record_id=record_id, pricing_model=model,
        policy_definition_hash=def_hash, line_items_canonical=lines_json,
    )
    db.flush()
    append_event(
        db, event_type="quote_revised" if previous else "quote_created", booking_id=booking.id,
        actor_role=initiator_role, actor_user_id=initiator.id if initiator else None,
        data=_quote_data(q, booking, previous.version if previous else None, extra), event_id=event_id,
    )
    db.add(q)
    db.flush()
    return q


def accept_quote(db: Session, booking: Booking, quote: PriceQuoteVersion, user: User, role: str) -> QuoteAcceptance:
    existing = acceptances(db, quote.id).get(role)
    if existing is not None:
        return existing
    quote_event = db.get(FinancialEvent, quote.financial_event_id)
    event_id = uuid4()
    append_event(
        db,
        event_type="quote_accepted",
        booking_id=booking.id,
        actor_role=role,
        actor_user_id=user.id,
        data={
            "quote_id": str(quote.id),
            "quote_version": quote.version,
            "quote_event_hash": quote_event.event_hash,
            "accepted_by_role": role,
            "customer_total_paise": quote.customer_total_paise,
            "worker_share_paise": quote.worker_share_paise,
            "platform_fee_paise": quote.platform_fee_paise,
        },
        event_id=event_id,
    )
    acceptance = QuoteAcceptance(quote_id=quote.id, booking_id=booking.id, user_id=user.id, role=role, financial_event_id=event_id)
    db.add(acceptance)
    db.flush()
    return acceptance


def ensure_quote(db: Session, booking: Booking) -> PriceQuoteVersion:
    """Return the current quote; for a pre-0005 booking, record its stored snapshot as a labelled legacy quote."""
    q = current_quote(db, booking.id)
    if q is not None:
        return q
    return create_quote(db, booking, source="legacy_snapshot", pricing_basis="legacy_booking_snapshot",
                        service_price_paise=booking.price_paise, initiator=None, initiator_role="system")


def check_quote_matches_booking(q: PriceQuoteVersion, booking: Booking) -> None:
    if (q.customer_total_paise, q.worker_share_paise, q.customer_total_paise - q.worker_share_paise) != (
        booking.price_paise, booking.payout_paise, booking.fee_paise
    ):
        raise ApiError(500, "PRICE_SNAPSHOT_MISMATCH", "The booking price does not match its agreed quote version.")


def revise_quote(db: Session, booking: Booking, user: User, role: str, service_price_paise: int) -> PriceQuoteVersion:
    if booking.status != "requested":
        raise conflict("PRICE_LOCKED", "A price can only be revised before the worker accepts the booking.")
    current = ensure_quote(db, booking)
    if service_price(current) == service_price_paise:
        raise unprocessable("QUOTE_UNCHANGED", "The proposed service price equals the current agreed service price.")
    q = create_quote(db, booking, source="revision", pricing_basis="revised_by_" + role,
                     service_price_paise=service_price_paise, initiator=user, initiator_role=role)
    accept_quote(db, booking, q, user, role)
    return q


def record_booking_event(db: Session, booking: Booking, event_type: str, actor: User | None, role: str, data: dict) -> FinancialEvent:
    return append_event(db, event_type=event_type, booking_id=booking.id, actor_role=role,
                        actor_user_id=actor.id if actor else None, data=data)


# --- ledger --------------------------------------------------------------------------------


def _assert_balanced(entries: list[dict], amount: int) -> None:
    debits = sum(e["amount_paise"] for e in entries if e["direction"] == "debit")
    credits = sum(e["amount_paise"] for e in entries if e["direction"] == "credit")
    if debits != credits or debits != amount or any(e["amount_paise"] <= 0 for e in entries):
        raise ApiError(500, "LEDGER_UNBALANCED", "Ledger postings do not balance; nothing was recorded.")


def _write_ledger(db: Session, tx: LedgerTransaction, entries: list[dict]) -> None:
    db.add(tx)
    db.flush()
    for i, e in enumerate(entries):
        db.add(LedgerEntry(transaction_id=tx.id, entry_index=i, account_code=e["account"], direction=e["direction"], amount_paise=e["amount_paise"]))
    db.flush()


def post_settlement(db: Session, booking: Booking, settlement: Settlement, actor: User) -> LedgerTransaction:
    """Atomic with the settlement insert (same transaction). Idempotent per booking."""
    key = f"booking-settlement:{booking.id}"
    existing = db.scalar(select(LedgerTransaction).where(LedgerTransaction.idempotency_key == key))
    if existing is not None:
        return existing
    q = ensure_quote(db, booking)
    check_quote_matches_booking(q, booking)
    if (settlement.gross_paise, settlement.fee_paise, settlement.payout_paise) != (
        q.customer_total_paise, q.customer_total_paise - q.worker_share_paise, q.worker_share_paise
    ):
        raise ApiError(500, "SETTLEMENT_MISMATCH", "Settlement does not reconcile with the agreed quote version.")
    entries = pricing.ledger_entries(_evaluation_of(q))
    amount = sum(e["amount_paise"] for e in entries if e["direction"] == "debit")
    _assert_balanced(entries, amount)
    tx_id, event_id = uuid4(), uuid4()
    append_event(
        db,
        event_type="simulated_settlement_recorded",
        booking_id=booking.id,
        actor_role="customer",
        actor_user_id=actor.id,
        settlement_id=settlement.id,
        event_id=event_id,
        data={
            "settlement_id": str(settlement.id),
            "quote_id": str(q.id),
            "quote_version": q.version,
            "is_simulated": True,
            "gross_paise": settlement.gross_paise,
            "platform_fee_paise": q.platform_fee_paise,
            "processing_charge_paise": q.additional_charges_paise,
            "worker_share_paise": settlement.payout_paise,
            "ledger_transaction": {
                "id": str(tx_id),
                "transaction_type": "simulated_booking_settlement",
                "idempotency_key": key,
                "amount_paise": amount,
                "entries": entries,
            },
        },
    )
    tx = LedgerTransaction(
        id=tx_id, booking_id=booking.id, settlement_id=settlement.id, transaction_type="simulated_booking_settlement",
        currency="INR", amount_paise=amount, idempotency_key=key, source_event_id=event_id,
        status="posted", is_simulated=True,
    )
    _write_ledger(db, tx, entries)
    return tx


def settlement_transaction(db: Session, booking_id: UUID) -> LedgerTransaction | None:
    return db.scalar(
        select(LedgerTransaction).where(
            LedgerTransaction.booking_id == booking_id, LedgerTransaction.transaction_type == "simulated_booking_settlement"
        )
    )


def reversal_of(db: Session, tx_id: UUID) -> LedgerTransaction | None:
    return db.scalar(select(LedgerTransaction).where(LedgerTransaction.reverses_transaction_id == tx_id))


def post_reversal(db: Session, booking: Booking, dispute: Dispute, reviewer: User) -> LedgerTransaction:
    original = settlement_transaction(db, booking.id)
    if original is None:
        raise conflict("NOTHING_TO_REVERSE", "This booking has no posted simulated settlement to reverse.")
    if reversal_of(db, original.id) is not None:
        raise conflict("ALREADY_REVERSED", "This simulated settlement has already been reversed.")
    flip = {"debit": "credit", "credit": "debit"}
    entries = [
        {"account": e.account_code, "direction": flip[e.direction], "amount_paise": e.amount_paise}
        for e in db.scalars(select(LedgerEntry).where(LedgerEntry.transaction_id == original.id).order_by(LedgerEntry.entry_index))
    ]
    _assert_balanced(entries, original.amount_paise)
    key = f"reversal:{original.id}"
    tx_id, event_id = uuid4(), uuid4()
    append_event(
        db,
        event_type="ledger_reversal_posted",
        booking_id=booking.id,
        actor_role="reviewer",
        actor_user_id=reviewer.id,
        dispute_id=dispute.id,
        event_id=event_id,
        data={
            "dispute_id": str(dispute.id),
            "reverses_transaction_id": str(original.id),
            "ledger_transaction": {
                "id": str(tx_id),
                "transaction_type": "simulated_settlement_reversal",
                "idempotency_key": key,
                "amount_paise": original.amount_paise,
                "entries": entries,
            },
        },
    )
    tx = LedgerTransaction(
        id=tx_id, booking_id=booking.id, settlement_id=None, reverses_transaction_id=original.id,
        transaction_type="simulated_settlement_reversal", currency="INR", amount_paise=original.amount_paise,
        idempotency_key=key, source_event_id=event_id, status="posted", is_simulated=True,
    )
    _write_ledger(db, tx, entries)
    return tx


# --- evidence views ------------------------------------------------------------------------


def _checkpoint_for(db: Session, sequence: int) -> AnchorCheckpoint | None:
    return db.scalar(
        select(AnchorCheckpoint).where(AnchorCheckpoint.first_sequence <= sequence, AnchorCheckpoint.last_sequence >= sequence)
    )


def anchor_status_for_events(db: Session, events: list[FinancialEvent]) -> dict:
    if not events:
        return {"status": None, "label": "No hash-chain evidence (legacy record)", "checkpoint_index": None, "tsa_gen_time": None,
                "events_externally_anchored": 0, "events_total": 0}
    statuses = []
    latest_cp = None
    for ev in events:
        cp = _checkpoint_for(db, ev.sequence)
        statuses.append(cp.anchor_status if cp else None)
        if ev is events[-1]:
            latest_cp = cp
    anchored = sum(1 for s in statuses if s == "EXTERNALLY_ANCHORED")
    if latest_cp is None:
        status = "ANCHOR_PENDING" if get_settings().tsa_configured else "LOCAL_ONLY"
    else:
        status = latest_cp.anchor_status
    label = STATUS_LABELS[status]
    if latest_cp is None:
        label += " (latest event not yet included in a checkpoint)"
    return {
        "status": status,
        "label": label,
        "checkpoint_index": latest_cp.checkpoint_index if latest_cp else None,
        "tsa_gen_time": latest_cp.tsa_gen_time if latest_cp and status == "EXTERNALLY_ANCHORED" else None,
        "events_externally_anchored": anchored,
        "events_total": len(events),
    }


def _line_view(lines: list[dict]) -> list[dict]:
    return [l | {"description": pricing.describe_component(l)} for l in lines]


def agreement_summary(db: Session, booking: Booking) -> dict:
    q = current_quote(db, booking.id)
    common = {"tax_note": TAX_NOTE, "processing_note": PROCESSING_NOTE, "additional_charges_note": PROCESSING_NOTE}
    if q is None:
        return {
            "evidence_level": "legacy",
            "note": LEGACY_NOTE,
            "quote_id": None, "quote_version": None, "source": None, "versions": 0,
            "service_price_paise": booking.price_paise,
            "customer_total_paise": booking.price_paise, "worker_share_paise": booking.payout_paise,
            "platform_fee_paise": booking.fee_paise, "additional_charges_paise": 0, "tax_paise": 0,
            "taxes_modeled": False, "fee_bps": booking.fee_bps, "fee_policy_id": None, "fee_policy_version": None,
            "pricing_model": None, "policy_definition_hash": None, "is_example_policy": None, "line_items": [],
            "currency": "INR", "created_at": None, "customer_accepted_at": None, "worker_accepted_at": None,
            "awaiting_acceptance_from": None, "matches_booking_snapshot": True, **common,
        }
    acc = acceptances(db, q.id)
    awaiting = None
    if booking.status == "requested":
        if "customer" not in acc and q.source != "legacy_snapshot":
            awaiting = "customer"
        elif "worker" not in acc:
            awaiting = "worker"
    fp = db.get(FeePolicy, q.fee_policy_record_id) if q.fee_policy_record_id else None
    return {
        "evidence_level": "legacy_snapshot" if q.source == "legacy_snapshot" else "versioned",
        "note": LEGACY_NOTE if q.source == "legacy_snapshot" else None,
        "quote_id": q.id, "quote_version": q.version, "source": q.source, "versions": q.version,
        "service_price_paise": service_price(q),
        "customer_total_paise": q.customer_total_paise, "worker_share_paise": q.worker_share_paise,
        "platform_fee_paise": q.platform_fee_paise, "additional_charges_paise": q.additional_charges_paise,
        "tax_paise": q.tax_paise, "taxes_modeled": q.taxes_modeled, "fee_bps": q.fee_bps,
        "fee_policy_id": q.fee_policy_id, "fee_policy_version": q.fee_policy_version, "currency": q.currency,
        "pricing_model": q.pricing_model or ("legacy_percentage" if q.source == "legacy_snapshot" else "percentage"),
        "policy_definition_hash": q.policy_definition_hash, "is_example_policy": fp.is_example if fp else None,
        "policy_label": fp.label if fp else None,
        "line_items": _line_view(quote_lines(q)),
        "created_at": q.created_at,
        "customer_accepted_at": acc["customer"].accepted_at if "customer" in acc else None,
        "worker_accepted_at": acc["worker"].accepted_at if "worker" in acc else None,
        "awaiting_acceptance_from": awaiting,
        "matches_booking_snapshot": (q.customer_total_paise, q.worker_share_paise, q.customer_total_paise - q.worker_share_paise)
        == (booking.price_paise, booking.payout_paise, booking.fee_paise),
        **common,
    }


def _tx_view(db: Session, tx: LedgerTransaction) -> dict:
    entries = list(db.scalars(select(LedgerEntry).where(LedgerEntry.transaction_id == tx.id).order_by(LedgerEntry.entry_index)))
    debits = sum(e.amount_paise for e in entries if e.direction == "debit")
    credits = sum(e.amount_paise for e in entries if e.direction == "credit")
    return {
        "id": tx.id, "transaction_type": tx.transaction_type, "amount_paise": tx.amount_paise, "currency": tx.currency,
        "idempotency_key": tx.idempotency_key, "settlement_id": tx.settlement_id,
        "reverses_transaction_id": tx.reverses_transaction_id, "is_simulated": tx.is_simulated, "created_at": tx.created_at,
        "entries": [{"index": e.entry_index, "account": e.account_code, "direction": e.direction, "amount_paise": e.amount_paise} for e in entries],
        "total_debits_paise": debits, "total_credits_paise": credits, "balanced": debits == credits == tx.amount_paise,
    }


def evidence_summary(db: Session, booking: Booking, settlement: Settlement | None) -> dict:
    events = booking_events(db, booking.id)
    tx = settlement_transaction(db, booking.id)
    reversed_tx = reversal_of(db, tx.id) if tx else None
    if tx is not None:
        ledger_status = "reversed" if reversed_tx else "posted"
    elif settlement is not None:
        ledger_status = "legacy_not_posted"
    else:
        ledger_status = "not_applicable_yet"
    balanced = _tx_view(db, tx)["balanced"] if tx else None
    return {
        "payment_evidence": PAYMENT_EVIDENCE,
        "payment_evidence_status": "SIMULATED",
        "ledger_status": ledger_status,
        "ledger_transaction_id": tx.id if tx else None,
        "ledger_balanced": balanced,
        "reversal_transaction_id": reversed_tx.id if reversed_tx else None,
        "event_count": len(events),
        "latest_event_hash": events[-1].event_hash if events else None,
        "anchor": anchor_status_for_events(db, events),
    }


def financial_record(db: Session, booking: Booking) -> dict:
    quotes = list(db.scalars(select(PriceQuoteVersion).where(PriceQuoteVersion.booking_id == booking.id).order_by(PriceQuoteVersion.version)))
    events = booking_events(db, booking.id)
    txs = list(db.scalars(select(LedgerTransaction).where(LedgerTransaction.booking_id == booking.id).order_by(LedgerTransaction.created_at)))
    settlement = db.scalar(select(Settlement).where(Settlement.booking_id == booking.id))
    return {
        "booking_id": booking.id,
        "booking_status": booking.status,
        "agreement": agreement_summary(db, booking),
        "quote_versions": [
            {
                "quote_id": q.id, "version": q.version, "source": q.source, "pricing_basis": q.pricing_basis,
                "customer_total_paise": q.customer_total_paise, "worker_share_paise": q.worker_share_paise,
                "platform_fee_paise": q.platform_fee_paise, "fee_bps": q.fee_bps, "initiated_by_role": q.initiated_by_role,
                "created_at": q.created_at,
                "acceptances": [{"role": a.role, "accepted_at": a.accepted_at} for a in acceptances(db, q.id).values()],
            }
            for q in quotes
        ],
        "settlement": (
            {"id": settlement.id, "gross_paise": settlement.gross_paise, "fee_paise": settlement.fee_paise,
             "payout_paise": settlement.payout_paise, "is_simulated": settlement.is_simulated,
             "label": SIMULATED_PAYMENT_LABEL, "created_at": settlement.created_at}
            if settlement else None
        ),
        "ledger_transactions": [_tx_view(db, tx) for tx in txs],
        "events": [
            {"sequence": e.sequence, "event_type": e.event_type, "event_hash": e.event_hash,
             "previous_event_hash": e.previous_event_hash, "created_at": e.created_at,
             "checkpoint_index": (cp.checkpoint_index if (cp := _checkpoint_for(db, e.sequence)) else None),
             "anchor_status": cp.anchor_status if cp else None}
            for e in events
        ],
        "evidence": evidence_summary(db, booking, settlement),
        "accounting_note": (
            "Demonstration accounting model. Entries record agreed allocations of a simulated payment; they are not "
            "bank receivables, recognised company revenue, or completed transfers."
        ),
    }


# --- portable receipt ----------------------------------------------------------------------


def _checkpoint_export(db: Session, cp: AnchorCheckpoint) -> dict:
    external = None
    if cp.anchor_status == "EXTERNALLY_ANCHORED":
        external = {
            "protocol": "RFC 3161",
            "tsa_name": cp.tsa_name, "tsa_url": cp.tsa_url, "request_nonce": cp.request_nonce,
            "time_stamp_response_der_b64": cp.tsa_response_b64,
            "gen_time": iso(cp.tsa_gen_time) if cp.tsa_gen_time else None,
            "serial_number": cp.tsa_serial, "policy_oid": cp.tsa_policy_oid, "signer_subject": cp.tsa_signer_subject,
            "server_trust_anchor_sha256": cp.tsa_ca_fingerprint,
        }
    return {
        "checkpoint_id": str(cp.id), "checkpoint_index": cp.checkpoint_index, "body": json.loads(cp.body_canonical),
        "digest": cp.digest, "anchor_status": cp.anchor_status, "external_timestamp": external,
    }


def receipt(db: Session, booking: Booking, role: str) -> dict:
    events = booking_events(db, booking.id)
    agreement = agreement_summary(db, booking)
    settlement = db.scalar(select(Settlement).where(Settlement.booking_id == booking.id))
    checkpoints: dict[int, AnchorCheckpoint] = {}
    exported_events = []
    for e in events:
        cp = _checkpoint_for(db, e.sequence)
        proof = None
        if cp is not None:
            checkpoints[cp.checkpoint_index] = cp
            hashes = list(db.scalars(
                select(FinancialEvent.event_hash)
                .where(FinancialEvent.sequence >= cp.first_sequence, FinancialEvent.sequence <= cp.last_sequence)
                .order_by(FinancialEvent.sequence)
            ))
            index = e.sequence - cp.first_sequence
            proof = {"checkpoint_index": cp.checkpoint_index, "leaf_index": index, "tree_size": len(hashes),
                     "path": crypto.inclusion_proof(hashes, index)}
        exported_events.append({
            "sequence": e.sequence, "event_type": e.event_type, "previous_event_hash": e.previous_event_hash,
            "payload": json.loads(e.payload_canonical), "payload_hash": e.payload_hash, "event_hash": e.event_hash,
            "inclusion_proof": proof,
        })
    txs = list(db.scalars(select(LedgerTransaction).where(LedgerTransaction.booking_id == booking.id).order_by(LedgerTransaction.created_at)))
    summary = {
        "booking_id": str(booking.id),
        "quote_version": agreement["quote_version"],
        "currency": "INR",
        "service_price_paise": agreement["service_price_paise"],
        "customer_total_paise": agreement["customer_total_paise"],
        "worker_share_paise": agreement["worker_share_paise"],
        "platform_fee_paise": agreement["platform_fee_paise"],
        "additional_charges_paise": agreement["additional_charges_paise"],
        "tax_paise": agreement["tax_paise"],
        "fee_bps": agreement["fee_bps"],
        "fee_policy_id": agreement["fee_policy_id"],
        "fee_policy_version": agreement["fee_policy_version"],
        "pricing_model": agreement["pricing_model"],
        "policy_definition_hash": agreement["policy_definition_hash"],
    }
    return {
        "receipt_format": crypto.RECEIPT_FORMAT,
        "generated_at": iso(datetime.now(timezone.utc)),
        "generated_for_role": role,
        "evidence_level": agreement["evidence_level"],
        "notice": (
            "Payments are SIMULATED. This receipt proves the integrity of the recorded price agreement and its "
            "allocations, and (if externally timestamped) that its checkpoint digest existed by the stated time. "
            "It does not prove that real money changed hands."
        ),
        "summary": summary,
        "booking": {
            "booking_id": str(booking.id), "origin": booking.origin, "status": booking.status,
            "skill_id": str(booking.skill_id), "starts_at": iso(booking.starts_at), "ends_at": iso(booking.ends_at),
            "repeat_of_booking_id": str(booking.repeat_of_booking_id) if booking.repeat_of_booking_id else None,
        },
        "agreement": {k: (str(v) if isinstance(v, (UUID, datetime)) else v) for k, v in agreement.items()},
        "settlement": (
            {"settlement_id": str(settlement.id), "gross_paise": settlement.gross_paise, "fee_paise": settlement.fee_paise,
             "payout_paise": settlement.payout_paise, "is_simulated": True, "label": SIMULATED_PAYMENT_LABEL}
            if settlement else None
        ),
        "ledger_transaction_ids": [str(t.id) for t in txs],
        "events": exported_events,
        "checkpoints": [_checkpoint_export(db, cp) for _, cp in sorted(checkpoints.items())],
        "hashing": {
            "canonicalization": "RFC 8785 (JCS); integers only, ASCII keys",
            "payload_hash": "SHA-256('SAHAKAR-SEVA:financial-event-payload:v1' || 0x00 || JCS(payload))",
            "event_hash": "SHA-256('SAHAKAR-SEVA:financial-event:v1' || 0x00 || uint64_be(sequence) || previous_event_hash || payload_hash)",
            "genesis_previous_event_hash": crypto.GENESIS_HASH,
            "merkle": "RFC 9162 §2.1.1: leaf = SHA-256(0x00 || event_hash), node = SHA-256(0x01 || left || right)",
            "checkpoint_digest": "SHA-256('SAHAKAR-SEVA:checkpoint:v1' || 0x00 || JCS(checkpoint body)); this digest is the RFC 3161 message imprint",
        },
        "verification": {
            "offline_command": "python3 scripts/verify_receipt.py <this-file>.json --tsa-ca <independently obtained TSA root certificate PEM>",
            "trust_anchor_note": (
                "Obtain the TSA root certificate yourself (for DigiCert: https://cacerts.digicert.com/DigiCertTrustedRootG4.crt) "
                "and compare its SHA-256 fingerprint. Never use a certificate taken from this file as the trust anchor."
            ),
            "independent_copy_note": "Keep this file. A later receipt can be compared with it: scripts/verify_receipt.py new.json --compare this.json",
        },
        "privacy": "Contains no names, addresses, phone numbers or free-text descriptions. User IDs are random identifiers.",
    }
