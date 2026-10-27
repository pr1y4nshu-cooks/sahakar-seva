"""Disputes and human review (MVP_MARKETPLACE_CONTRACT §8).

Reviewer rights come only from the ``platform_reviewers`` table, which no API can write. A reviewer
can never resolve a dispute on a booking where they are a party. No automated sanction exists.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.errors import conflict, forbidden, not_found
from app.models.marketplace import Booking, Dispute, PlatformReviewer
from app.models.service_taxonomy import Skill
from app.models.user import User, WorkerProfile
from app.repositories import marketplace_repository as mrepo
from app.services import booking_service
from app.services.marketplace_common import audit, utcnow


def is_reviewer(db: Session, user: User) -> bool:
    return db.get(PlatformReviewer, user.id) is not None


def open_dispute(db: Session, user: User, booking_id: UUID, description: str) -> dict:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise not_found("Booking not found.")
    role = booking_service._role(db, booking, user)
    if role is None:
        raise not_found("Booking not found.")
    booking = mrepo.lock_booking(db, booking_id)
    if booking.status not in booking_service.DISPUTABLE:
        raise conflict("INVALID_TRANSITION", f"A '{booking.status}' booking cannot be disputed.")
    previous = booking.status
    dispute = Dispute(booking_id=booking.id, opened_by_user_id=user.id, description=description, status="open")
    try:
        with db.begin_nested():
            db.add(dispute)
            booking.status = "disputed"
            db.flush()
        audit(db, "dispute", dispute.id, user.id, "opened", {"booking_id": str(booking.id), "by": role, "booking_was": previous})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("DISPUTE_EXISTS", "A dispute has already been opened for this booking.") from exc
    return booking_service.get_booking(db, user, booking_id)


def _queue_item(db: Session, d: Dispute, reviewer: User) -> dict:
    b = d.booking
    worker = db.get(WorkerProfile, b.worker_profile_id)
    customer = db.get(User, b.customer_user_id)
    party = reviewer.id in (b.customer_user_id, worker.user_id)
    return {
        "id": d.id,
        "booking_id": b.id,
        "status": d.status,
        "description": d.description,
        "opened_by_role": "customer" if d.opened_by_user_id == b.customer_user_id else "worker",
        "booking_status": b.status,
        "skill_name": b.skill.name,
        "locality": b.locality,  # exact address is not needed for review
        "starts_at": b.starts_at,
        "price_paise": b.price_paise,
        "customer_display_name": customer.display_name,
        "worker_display_name": worker.display_name,
        "can_resolve": d.status == "open" and not party,
        "outcome": d.outcome,
        "resolution_reason": d.resolution_reason,
        "resolved_at": d.resolved_at,
        "created_at": d.created_at,
    }


def review_queue(db: Session, user: User) -> list[dict]:
    if not is_reviewer(db, user):
        raise forbidden("Only authorised dispute reviewers can view the review queue.")
    disputes = db.scalars(
        select(Dispute)
        .options(joinedload(Dispute.booking).joinedload(Booking.skill).joinedload(Skill.category))
        .order_by(Dispute.status, Dispute.created_at)
    )
    return [_queue_item(db, d, user) for d in disputes]


def resolve(db: Session, user: User, dispute_id: UUID, outcome: str, reason: str) -> dict:
    if not is_reviewer(db, user):
        raise forbidden("Only authorised dispute reviewers can resolve disputes.")
    dispute = db.scalar(select(Dispute).where(Dispute.id == dispute_id).with_for_update())
    if dispute is None:
        raise not_found("Dispute not found.")
    booking = db.get(Booking, dispute.booking_id)
    worker = db.get(WorkerProfile, booking.worker_profile_id)
    if user.id in (booking.customer_user_id, worker.user_id):
        raise forbidden("You are a party to this booking and cannot review its dispute.")
    if dispute.status != "open":
        raise conflict("INVALID_TRANSITION", "This dispute has already been resolved.")
    dispute.status = "resolved"
    dispute.outcome = outcome
    dispute.resolution_reason = reason
    dispute.reviewer_user_id = user.id
    dispute.resolved_at = utcnow()
    audit(db, "dispute", dispute.id, user.id, "resolved", {"outcome": outcome, "reason": reason})
    db.commit()
    return _queue_item(db, db.scalar(select(Dispute).where(Dispute.id == dispute_id)), user)


def my_disputes(db: Session, user: User) -> list[dict]:
    return [b for b in booking_service.list_my_bookings(db, user, None) if b["dispute"] is not None]
