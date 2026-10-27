"""Shared booking lifecycle for direct hire and job applications (MVP_MARKETPLACE_CONTRACT §6).

Concurrency: ``accept`` row-locks the worker profile and the booking, re-checks overlaps, and relies on
the ``ex_bookings_worker_no_overlap`` exclusion constraint as the final, database-level guarantee.
"""

from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.errors import ApiError, conflict, forbidden, not_found, unprocessable
from app.models.marketplace import (
    SIMULATED_PAYMENT_LABEL,
    AvailabilitySlot,
    Booking,
    Dispute,
    Job,
    JobApplication,
    Settlement,
)
from app.models.service_taxonomy import Skill
from app.models.user import User, WorkerProfile
from app.repositories import marketplace_repository as mrepo
from app.repositories.worker_repository import get_worker_profile_by_user
from app.services.marketplace_common import (
    audit,
    compute_fee_split,
    price_for_slot,
    utcnow,
    verification_label,
)
from app.services.worker_setup_service import ensure_discoverable, skill_dict, worker_declares_skill

# action -> (allowed from-states, to-state, actor)
TRANSITIONS: dict[str, tuple[frozenset[str], str, str]] = {
    "accept": (frozenset({"requested"}), "confirmed", "worker"),
    "decline": (frozenset({"requested"}), "declined", "worker"),
    "start": (frozenset({"confirmed"}), "in_progress", "worker"),
    "complete": (frozenset({"in_progress"}), "completed", "customer"),
}
CANCEL_FROM = {"customer": frozenset({"requested", "confirmed"}), "worker": frozenset({"confirmed"})}
DISPUTABLE = frozenset({"confirmed", "in_progress", "completed"})
ADDRESS_VISIBLE_TO_WORKER = frozenset({"confirmed", "in_progress", "completed", "disputed"})


def fee_policy_text(fee_bps: int) -> str:
    return f"Pilot assumption: {fee_bps / 100:g}% platform fee (configurable, capped at {get_settings().platform_fee_cap_bps / 100:g}%)."


def _role(db: Session, booking: Booking, user: User) -> str | None:
    if booking.customer_user_id == user.id:
        return "customer"
    profile = get_worker_profile_by_user(db, user.id)
    if profile is not None and booking.worker_profile_id == profile.id:
        return "worker"
    return None


def allowed_actions(booking: Booking, role: str, has_dispute: bool) -> list[str]:
    actions = [a for a, (src, _dst, actor) in TRANSITIONS.items() if booking.status in src and actor == role]
    if booking.status in CANCEL_FROM[role]:
        actions.append("cancel")
    if booking.status in DISPUTABLE and not has_dispute:
        actions.append("dispute")
    return actions


def _settlement_dict(s: Settlement) -> dict:
    return {
        "id": s.id,
        "gross_paise": s.gross_paise,
        "fee_bps": s.fee_bps,
        "fee_paise": s.fee_paise,
        "payout_paise": s.payout_paise,
        "status": s.status,
        "is_simulated": s.is_simulated,
        "label": SIMULATED_PAYMENT_LABEL,
        "created_at": s.created_at,
    }


def booking_view(db: Session, booking: Booking, user: User, role: str | None = None) -> dict:
    role = role or _role(db, booking, user)
    if role is None:
        raise not_found("Booking not found.")
    settlement = db.scalar(select(Settlement).where(Settlement.booking_id == booking.id))
    dispute = db.scalar(select(Dispute).where(Dispute.booking_id == booking.id))
    worker = booking.worker_profile
    show_address = role == "customer" or booking.status in ADDRESS_VISIBLE_TO_WORKER
    return {
        "id": booking.id,
        "origin": booking.origin,
        "status": booking.status,
        "my_role": role,
        "job_id": booking.job_id,
        "skill": skill_dict(booking.skill),
        "worker_profile_id": booking.worker_profile_id,
        "worker_display_name": worker.display_name,
        "worker_verification_label": verification_label(worker.onboarding_status),
        "customer_display_name": booking.customer.display_name,
        "starts_at": booking.starts_at,
        "ends_at": booking.ends_at,
        "locality": booking.locality,
        "address_details": booking.address_details if show_address else None,
        "address_hidden_reason": None if show_address else "The exact address is shared after you accept the booking.",
        "customer_notes": booking.customer_notes,
        "price": {
            "price_paise": booking.price_paise,
            "fee_bps": booking.fee_bps,
            "fee_paise": booking.fee_paise,
            "payout_paise": booking.payout_paise,
            "fee_policy": fee_policy_text(booking.fee_bps),
        },
        "settlement": _settlement_dict(settlement) if settlement else None,
        "dispute": (
            {
                "id": dispute.id,
                "status": dispute.status,
                "description": dispute.description,
                "outcome": dispute.outcome,
                "resolution_reason": dispute.resolution_reason,
                "resolved_at": dispute.resolved_at,
                "opened_by_me": dispute.opened_by_user_id == user.id,
            }
            if dispute
            else None
        ),
        "allowed_actions": allowed_actions(booking, role, dispute is not None),
        "created_at": booking.created_at,
        "updated_at": booking.updated_at,
    }


def _load(db: Session, booking_id: UUID) -> Booking | None:
    return db.scalar(
        select(Booking)
        .options(
            joinedload(Booking.skill).joinedload(Skill.category),
            joinedload(Booking.worker_profile),
            joinedload(Booking.customer),
        )
        .where(Booking.id == booking_id)
    )


def get_booking(db: Session, user: User, booking_id: UUID) -> dict:
    booking = _load(db, booking_id)
    if booking is None:
        raise not_found("Booking not found.")
    return booking_view(db, booking, user)


def list_my_bookings(db: Session, user: User, role: str | None) -> list[dict]:
    profile = get_worker_profile_by_user(db, user.id)
    conditions = []
    if role in (None, "customer"):
        conditions.append(Booking.customer_user_id == user.id)
    if role in (None, "worker") and profile is not None:
        conditions.append(Booking.worker_profile_id == profile.id)
    if not conditions:
        return []
    bookings = db.scalars(
        select(Booking)
        .options(
            joinedload(Booking.skill).joinedload(Skill.category),
            joinedload(Booking.worker_profile),
            joinedload(Booking.customer),
        )
        .where(or_(*conditions))
        .order_by(Booking.starts_at.desc())
    ).unique()
    return [booking_view(db, b, user) for b in bookings]


# --- creation ---------------------------------------------------------------------------


def create_direct_booking(db: Session, customer: User, payload) -> dict:
    worker = db.get(WorkerProfile, payload.worker_profile_id)
    if worker is None:
        raise not_found("Worker not found.")
    if worker.user_id == customer.id:
        raise unprocessable("SELF_BOOKING", "You cannot book yourself.")
    settings = ensure_discoverable(db, worker.id, worker.onboarding_status)
    if not worker_declares_skill(db, worker.id, payload.skill_id):
        raise unprocessable("SKILL_NOT_OFFERED", "This worker has not declared that skill.")

    slot = db.get(AvailabilitySlot, payload.slot_id)
    if slot is None or slot.worker_profile_id != worker.id or not slot.is_active:
        raise unprocessable("SLOT_UNAVAILABLE", "That availability slot is not offered by this worker.")
    if slot.starts_at <= utcnow():
        raise unprocessable("SLOT_UNAVAILABLE", "That slot has already started.")
    if mrepo.has_active_overlap(db, worker.id, slot.starts_at, slot.ends_at):
        raise conflict("SLOT_UNAVAILABLE", "That slot is already booked.")
    if mrepo.point_within_worker_radius(db, worker.id, payload.latitude, payload.longitude) is None:
        raise unprocessable("OUTSIDE_SERVICE_AREA", "This location is outside the worker's service area.")
    duplicate = db.scalar(
        select(Booking.id).where(
            Booking.slot_id == slot.id,
            Booking.customer_user_id == customer.id,
            Booking.status.in_(("requested", "confirmed", "in_progress")),
        )
    )
    if duplicate is not None:
        raise conflict("DUPLICATE_REQUEST", "You already have an active request for this slot.")

    price = price_for_slot(settings.hourly_rate_paise, slot.starts_at, slot.ends_at)
    fee_bps, fee_paise, payout = compute_fee_split(price)
    booking = Booking(
        customer_user_id=customer.id,
        worker_profile_id=worker.id,
        origin="direct",
        slot_id=slot.id,
        skill_id=payload.skill_id,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        locality=payload.locality,
        address_details=payload.address_details.strip(),
        customer_notes=(payload.customer_notes or "").strip() or None,
        price_paise=price,
        fee_bps=fee_bps,
        fee_paise=fee_paise,
        payout_paise=payout,
        status="requested",
    )
    db.add(booking)
    db.flush()
    audit(db, "booking", booking.id, customer.id, "requested", {"origin": "direct", "price_paise": price})
    db.commit()
    return get_booking(db, customer, booking.id)


def create_job_booking(db: Session, job: Job, application: JobApplication, actor: User) -> Booking:
    """Called by the job service with the job row already locked. Caller commits."""
    fee_bps, fee_paise, payout = compute_fee_split(job.budget_paise)
    booking = Booking(
        customer_user_id=job.customer_user_id,
        worker_profile_id=application.worker_profile_id,
        origin="job",
        job_id=job.id,
        application_id=application.id,
        skill_id=job.skill_id,
        starts_at=job.starts_at,
        ends_at=job.ends_at,
        locality=job.locality,
        address_details=job.address_details,
        price_paise=job.budget_paise,
        fee_bps=fee_bps,
        fee_paise=fee_paise,
        payout_paise=payout,
        status="requested",
    )
    db.add(booking)
    db.flush()
    audit(db, "booking", booking.id, actor.id, "requested", {"origin": "job", "job_id": str(job.id), "price_paise": job.budget_paise})
    return booking


# --- transitions ------------------------------------------------------------------------


def _job_side_effects(db: Session, booking: Booking, new_status: str, actor_role: str) -> None:
    if booking.origin != "job":
        return
    if new_status == "confirmed":
        db.execute(
            update(JobApplication)
            .where(JobApplication.job_id == booking.job_id, JobApplication.id != booking.application_id, JobApplication.status == "applied")
            .values(status="rejected")
        )
    elif new_status in ("declined", "cancelled"):
        job = mrepo.lock_job(db, booking.job_id)
        if job is not None and job.status == "filled":
            job.status = "open"
        application = db.get(JobApplication, booking.application_id)
        if application is not None and application.status == "selected":
            application.status = "rejected" if actor_role == "customer" else "withdrawn"


def transition(db: Session, user: User, booking_id: UUID, action: str) -> dict:
    if action not in TRANSITIONS and action != "cancel":
        raise not_found("Unknown booking action.")
    booking = _load(db, booking_id)
    if booking is None:
        raise not_found("Booking not found.")
    role = _role(db, booking, user)
    if role is None:
        raise not_found("Booking not found.")

    if action == "accept":
        # Serialise confirmations per worker before re-reading state.
        mrepo.lock_worker_profile(db, booking.worker_profile_id)
    booking = mrepo.lock_booking(db, booking_id)

    if action == "cancel":
        allowed_from, new_status = CANCEL_FROM[role], "cancelled"
    else:
        allowed_from, new_status, actor = TRANSITIONS[action]
        if actor != role:
            raise forbidden(f"Only the {actor} can {action} this booking.")
    if booking.status not in allowed_from:
        raise conflict("INVALID_TRANSITION", f"Cannot {action} a booking that is '{booking.status}'.")

    if action == "accept":
        if booking.slot_id is not None:
            slot = db.get(AvailabilitySlot, booking.slot_id)
            if slot is None or not slot.is_active:
                raise conflict("SLOT_UNAVAILABLE", "The availability slot for this booking was removed.")
        if mrepo.has_active_overlap(db, booking.worker_profile_id, booking.starts_at, booking.ends_at, booking.id):
            raise conflict("BOOKING_CONFLICT", "You already have a confirmed booking at this time.")

    previous = booking.status
    booking.status = new_status
    try:
        with db.begin_nested():
            db.flush()
            _job_side_effects(db, booking, new_status, role)
            if new_status == "completed":
                _record_settlement(db, booking)
            audit(db, "booking", booking.id, user.id, action, {"from": previous, "to": new_status})
            db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("BOOKING_CONFLICT", "This booking conflicts with another confirmed booking.") from exc
    db.expire_all()
    return get_booking(db, user, booking_id)


def _record_settlement(db: Session, booking: Booking) -> Settlement:
    """Exactly one immutable simulated settlement per completed booking (UNIQUE booking_id)."""
    fee_bps, fee_paise, payout = compute_fee_split(booking.price_paise, booking.fee_bps)
    if (fee_paise, payout) != (booking.fee_paise, booking.payout_paise):
        raise ApiError(500, "SETTLEMENT_MISMATCH", "Settlement does not reconcile with the agreed price breakdown.")
    settlement = Settlement(
        booking_id=booking.id,
        gross_paise=booking.price_paise,
        fee_bps=fee_bps,
        fee_paise=fee_paise,
        payout_paise=payout,
        is_simulated=True,
        status="simulated_settled",
    )
    db.add(settlement)
    db.flush()
    audit(db, "settlement", settlement.id, None, "simulated_settlement_recorded",
          {"booking_id": str(booking.id), "gross_paise": booking.price_paise, "fee_paise": fee_paise, "payout_paise": payout})
    return settlement


# --- earnings ---------------------------------------------------------------------------


def earnings(db: Session, user: User) -> dict:
    profile = get_worker_profile_by_user(db, user.id)
    rows = []
    if profile is not None:
        rows = list(
            db.execute(
                select(Settlement, Booking)
                .join(Booking, Booking.id == Settlement.booking_id)
                .where(Booking.worker_profile_id == profile.id)
                .order_by(Settlement.created_at.desc())
            )
        )
    items = [
        {**_settlement_dict(s), "booking_id": b.id, "starts_at": b.starts_at, "locality": b.locality}
        for s, b in rows
    ]
    gross = sum(i["gross_paise"] for i in items)
    fee = sum(i["fee_paise"] for i in items)
    payout = sum(i["payout_paise"] for i in items)
    return {
        "label": SIMULATED_PAYMENT_LABEL,
        "fee_policy": fee_policy_text(get_settings().platform_fee_bps),
        "totals": {"gross_paise": gross, "fee_paise": fee, "payout_paise": payout, "count": len(items), "reconciles": gross == fee + payout},
        "settlements": items,
    }
